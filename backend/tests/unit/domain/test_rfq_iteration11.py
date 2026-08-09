from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.domain.rfqs.entities import RfqRequest, build_send_idempotency_key
from app.domain.rfqs.exceptions import InvalidRfqState
from app.domain.rfqs.value_objects import RfqStatus


def make_rfq() -> RfqRequest:
    return RfqRequest(
        tender_id=uuid4(),
        tender_supplier_id=uuid4(),
        supplier_id=uuid4(),
        contact_id=uuid4(),
        catalog_snapshot_id=uuid4(),
        generated_by_user_id=uuid4(),
        response_deadline=datetime.now(UTC) + timedelta(days=3),
        template_name="supplier_rfq",
        template_version="2.0.0",
        subject="Solicitud de cotización",
        body="Favor de cotizar el producto seleccionado.",
        products=({"product_id": str(uuid4()), "name": "Cable"},),
        generation_key="a" * 64,
        to_recipients=("ventas@example.mx",),
    )


def test_send_idempotency_key_depends_on_version_recipient_and_intent() -> None:
    rfq_id = uuid4()
    first = build_send_idempotency_key(rfq_id, 1, ("VENTAS@example.mx",))
    assert first == build_send_idempotency_key(rfq_id, 1, ("ventas@example.mx",))
    assert first != build_send_idempotency_key(rfq_id, 2, ("ventas@example.mx",))
    assert first != build_send_idempotency_key(rfq_id, 1, ("otro@example.mx",))
    assert first != build_send_idempotency_key(
        rfq_id,
        1,
        ("ventas@example.mx",),
        "different_intent",
    )


def test_rfq_requires_review_approval_and_queue_before_sending() -> None:
    rfq = make_rfq()
    with pytest.raises(InvalidRfqState):
        rfq.queue(uuid4())
    rfq.start_review()
    rfq.approve(uuid4(), ())
    assert rfq.status is RfqStatus.APPROVED
    rfq.queue(uuid4())
    rfq.start_sending()
    assert rfq.status is RfqStatus.SENDING


def test_edit_after_review_invalidates_review_and_creates_new_version() -> None:
    rfq = make_rfq()
    rfq.start_review()
    rfq.edit(subject="Solicitud de cotización actualizada")
    assert rfq.status is RfqStatus.DRAFT
    assert rfq.version == 2
    assert rfq.approved_at is None
    assert rfq.send_idempotency_key is None


def test_sent_rfq_is_immutable() -> None:
    rfq = make_rfq()
    rfq.start_review()
    rfq.approve(uuid4(), ())
    rfq.queue(uuid4())
    rfq.start_sending()
    rfq.mark_sent()
    with pytest.raises(InvalidRfqState):
        rfq.edit(subject="No permitido")
