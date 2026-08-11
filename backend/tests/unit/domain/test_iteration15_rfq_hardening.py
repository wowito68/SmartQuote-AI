from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.domain.rfqs.entities import (
    EmailAttachment,
    EmailMessage,
    EmailTemplate,
    OutboundMessageLog,
    RfqRequest,
    RfqTaskRecord,
    RfqVersionSnapshot,
)
from app.domain.rfqs.exceptions import AttachmentValidationError, InvalidRfqState
from app.domain.rfqs.value_objects import (
    EmailMessageStatus,
    OutboundLogResult,
    RfqStatus,
    TaskRecordStatus,
)
from app.domain.shared.exceptions import ValidationError


def _rfq(**changes) -> RfqRequest:
    values = {
        "tender_id": uuid4(),
        "tender_supplier_id": uuid4(),
        "supplier_id": uuid4(),
        "catalog_snapshot_id": uuid4(),
        "generated_by_user_id": uuid4(),
        "response_deadline": datetime.now(UTC) + timedelta(days=7),
        "template_name": "rfq",
        "template_version": "1",
        "subject": "Request for quotation",
        "body": "Please provide your quotation.",
        "products": ({"name": "Sensor", "quantity": "2"},),
        "generation_key": "d" * 64,
        "to_recipients": ("BUYER@EXAMPLE.COM", "buyer@example.com"),
    }
    values.update(changes)
    return RfqRequest(**values)


def test_email_template_and_attachment_validation() -> None:
    template = EmailTemplate("rfq", "1", "Subject", "Body", "text/html")
    assert template.content_type == "text/html"
    for args in (
        ("", "1", "Subject", "Body", "text/plain"),
        ("rfq", "1", " ", "Body", "text/plain"),
        ("rfq", "1", "Subject", "Body", "application/json"),
    ):
        with pytest.raises(ValidationError):
            EmailTemplate(*args)

    values = {
        "rfq_id": uuid4(),
        "document_id": uuid4(),
        "original_file_name": "spec.pdf",
        "file_hash": "a" * 64,
        "file_size": 10,
        "mime_type": "application/pdf",
    }
    attachment = EmailAttachment(**values)
    assert attachment.snapshot()["name"] == "spec.pdf"
    for changes in (
        {"original_file_name": "../spec.pdf"},
        {"file_hash": "bad"},
        {"file_size": 0},
        {"mime_type": "text/plain"},
    ):
        with pytest.raises(AttachmentValidationError):
            EmailAttachment(**{**values, **changes})


def test_rfq_validates_and_covers_review_edit_delivery_lifecycle() -> None:
    for changes in (
        {"response_deadline": datetime.now(UTC) - timedelta(days=1)},
        {"template_name": " "},
        {"subject": " "},
        {"body": " "},
        {"products": ()},
        {"generation_key": "bad"},
        {"generation_duration_ms": -1},
    ):
        with pytest.raises(ValidationError):
            _rfq(**changes)

    rfq = _rfq()
    assert rfq.to_recipients == ("buyer@example.com",)
    rfq.start_review()
    rfq.edit(
        subject="Updated RFQ",
        body="Updated body",
        to_recipients=("sales@example.com",),
        cc_recipients=("copy@example.com",),
        bcc_recipients=("audit@example.com",),
        response_deadline=datetime.now(UTC) + timedelta(days=10),
        observations=" priority ",
        contact_name=" Sales Team ",
    )
    assert rfq.status is RfqStatus.DRAFT and rfq.version == 2
    rfq.start_review()
    rfq.reject_review()
    rfq.record_attachment_edit()
    rfq.start_review()
    rfq.approve(uuid4(), ())
    assert rfq.status is RfqStatus.APPROVED and rfq.send_idempotency_key
    with pytest.raises(InvalidRfqState):
        rfq.edit(subject="too late")
    rfq.queue(uuid4())
    rfq.start_sending()
    rfq.mark_sent()
    rfq.mark_delivered()
    assert rfq.status is RfqStatus.DELIVERED
    with pytest.raises(InvalidRfqState):
        rfq.cancel(uuid4(), "late")


def test_rfq_failure_retry_cancel_and_approval_guards() -> None:
    no_recipient = _rfq(to_recipients=())
    no_recipient.start_review()
    with pytest.raises(ValidationError):
        no_recipient.approve(uuid4(), ())
    with pytest.raises(InvalidRfqState):
        no_recipient.queue(uuid4())

    rfq = _rfq()
    rfq.start_review()
    rfq.approve(uuid4(), ())
    rfq.queue(uuid4())
    rfq.mark_failed(" smtp unavailable ")
    rfq.mark_retry_pending(" retry later ")
    assert rfq.status is RfqStatus.RETRY_PENDING
    rfq.queue(uuid4())
    rfq.cancel(uuid4(), " operator cancelled ")
    assert rfq.status is RfqStatus.CANCELLED
    with pytest.raises(InvalidRfqState):
        rfq.start_review()


def test_rfq_snapshot_email_task_and_outbound_log_guards() -> None:
    snapshot = RfqVersionSnapshot(
        rfq_id=uuid4(),
        version=1,
        changed_by_user_id=uuid4(),
        status=RfqStatus.DRAFT,
        contact_id=None,
        subject="Subject",
        body="Body",
        to_recipients=("A@example.com",),
        cc_recipients=(),
        bcc_recipients=(),
        products=({"name": "Sensor"},),
        attachment_snapshot=(),
        change_reason=" edit ",
    )
    assert snapshot.to_recipients == ("a@example.com",)
    with pytest.raises(ValidationError):
        RfqVersionSnapshot(
            rfq_id=uuid4(),
            version=0,
            changed_by_user_id=uuid4(),
            status=RfqStatus.DRAFT,
            contact_id=None,
            subject="Subject",
            body="Body",
            to_recipients=(),
            cc_recipients=(),
            bcc_recipients=(),
            products=(),
            attachment_snapshot=(),
        )

    values = {
        "rfq_id": uuid4(),
        "rfq_version": 1,
        "attempt_number": 1,
        "idempotency_key": "f" * 64,
        "provider_name": "simulation",
        "from_address": "Sender@Example.com",
        "to_recipients": ("Buyer@Example.com",),
        "cc_recipients": (),
        "bcc_recipients": (),
        "subject": "Subject",
        "body": "Body",
        "attachment_snapshot": (),
    }
    message = EmailMessage(**values)
    message.start()
    message.succeed(" msg-1 ", -3)
    assert message.status is EmailMessageStatus.SENT and message.duration_ms == 0
    with pytest.raises(InvalidRfqState):
        message.start()
    failed = EmailMessage(**{**values, "id": uuid4(), "attempt_number": 2})
    with pytest.raises(InvalidRfqState):
        failed.fail(RuntimeError("not started"), 1)
    failed.start()
    failed.fail(RuntimeError("smtp failed"), -1)
    assert failed.status is EmailMessageStatus.FAILED and failed.duration_ms == 0

    task = RfqTaskRecord(rfq_id=uuid4(), correlation_id=" corr ")
    task.start()
    task.retry(" temporary ")
    assert task.status is TaskRecordStatus.RETRY_PENDING
    task.start()
    task.fail(" permanent ")
    assert task.status is TaskRecordStatus.FAILED
    task.succeed()
    assert task.status is TaskRecordStatus.SUCCEEDED
    with pytest.raises(ValidationError):
        RfqTaskRecord(rfq_id=uuid4(), correlation_id=" ")

    log = OutboundMessageLog(
        rfq_id=uuid4(),
        email_message_id=uuid4(),
        event_type="sent",
        result=OutboundLogResult.SUCCESS,
        provider_name="simulation",
        details={},
    )
    assert log.event_type == "sent"
    with pytest.raises(ValidationError):
        OutboundMessageLog(
            rfq_id=uuid4(),
            email_message_id=uuid4(),
            event_type=" ",
            result=OutboundLogResult.FAILURE,
            provider_name="simulation",
            details={},
        )
