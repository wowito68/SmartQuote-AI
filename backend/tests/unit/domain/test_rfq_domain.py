from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.domain.rfqs.entities import EmailAttachment, EmailMessage, RfqRequest
from app.domain.rfqs.exceptions import AttachmentValidationError, InvalidRfqState
from app.domain.rfqs.value_objects import EmailMessageStatus, RfqStatus
from app.domain.shared.exceptions import ValidationError


def make_attachment(rfq_id=None) -> EmailAttachment:
    return EmailAttachment(
        rfq_id=rfq_id or uuid4(),
        document_id=uuid4(),
        original_file_name="anexo.pdf",
        file_hash="a" * 64,
        file_size=128,
        mime_type="application/pdf",
    )


def make_rfq(*, recipients=("ventas@example.mx",)) -> RfqRequest:
    now = datetime.now(UTC)
    item = RfqRequest(
        tender_id=uuid4(),
        tender_supplier_id=uuid4(),
        supplier_id=uuid4(),
        catalog_snapshot_id=uuid4(),
        generated_by_user_id=uuid4(),
        response_deadline=now + timedelta(days=5),
        template_name="supplier_rfq",
        template_version="1.0.0",
        subject="Solicitud de cotización",
        body="Favor de cotizar el producto solicitado.",
        products=({"product_id": str(uuid4()), "name": "Cable"},),
        generation_key="b" * 64,
        to_recipients=recipients,
        created_at=now,
        updated_at=now,
    )
    item.start_review()
    return item


def test_rfq_state_machine_freezes_content_after_approval() -> None:
    rfq = make_rfq()
    rfq.edit(subject="Solicitud actualizada", cc_recipients=("compras@example.mx",))
    assert rfq.version == 2
    attachment = make_attachment(rfq.id)
    reviewer = uuid4()
    rfq.approve(reviewer, (attachment,))
    assert rfq.status is RfqStatus.APPROVED
    assert rfq.approved_by_user_id == reviewer
    assert rfq.send_idempotency_key is not None
    with pytest.raises(InvalidRfqState):
        rfq.edit(subject="No permitido")
    rfq.queue(uuid4())
    rfq.start_sending()
    rfq.mark_sent()
    assert rfq.status is RfqStatus.SENT
    with pytest.raises(InvalidRfqState):
        rfq.queue(uuid4())


def test_rfq_requires_primary_recipient_before_approval_and_allows_failed_retry() -> None:
    rfq = make_rfq(recipients=())
    with pytest.raises(ValidationError):
        rfq.approve(uuid4(), ())
    rfq.edit(to_recipients=("VENTAS@EXAMPLE.MX",))
    rfq.approve(uuid4(), ())
    sender = uuid4()
    rfq.queue(sender)
    rfq.start_sending()
    rfq.mark_failed("SMTP timeout")
    assert rfq.status is RfqStatus.FAILED
    rfq.queue(sender)
    assert rfq.status is RfqStatus.QUEUED


def test_attachment_validates_name_hash_size_and_mime() -> None:
    with pytest.raises(AttachmentValidationError):
        make_attachment().__class__(
            rfq_id=uuid4(),
            document_id=uuid4(),
            original_file_name="../secret.pdf",
            file_hash="a" * 64,
            file_size=10,
            mime_type="application/pdf",
        )
    with pytest.raises(AttachmentValidationError):
        EmailAttachment(
            rfq_id=uuid4(),
            document_id=uuid4(),
            original_file_name="anexo.pdf",
            file_hash="not-a-hash",
            file_size=10,
            mime_type="application/pdf",
        )
    with pytest.raises(AttachmentValidationError):
        EmailAttachment(
            rfq_id=uuid4(),
            document_id=uuid4(),
            original_file_name="anexo.pdf",
            file_hash="a" * 64,
            file_size=10,
            mime_type="text/plain",
        )


def test_email_message_records_attempt_result() -> None:
    message = EmailMessage(
        rfq_id=uuid4(),
        rfq_version=3,
        attempt_number=1,
        idempotency_key="c" * 64,
        provider_name="smtp",
        from_address="compras@example.mx",
        to_recipients=("ventas@example.mx",),
        cc_recipients=(),
        bcc_recipients=(),
        subject="RFQ",
        body="Contenido",
        attachment_snapshot=(),
    )
    message.start()
    message.succeed("<message@example.mx>", 42)
    assert message.status is EmailMessageStatus.SENT
    assert message.duration_ms == 42
    assert message.external_message_id == "<message@example.mx>"
