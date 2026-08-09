from datetime import UTC, datetime
from uuid import uuid4

from app.domain.rfqs.entities import EmailMessage
from app.infrastructure.email.simulated_email_sender import SimulatedEmailSender


def test_simulated_sender_never_needs_network_and_returns_stable_provider_result() -> None:
    message = EmailMessage(
        rfq_id=uuid4(),
        rfq_version=1,
        attempt_number=1,
        idempotency_key="b" * 64,
        provider_name="simulation",
        from_address="compras@example.mx",
        to_recipients=("ventas@example.mx",),
        cc_recipients=(),
        bcc_recipients=(),
        subject="RFQ",
        body="Cotización solicitada",
        attachment_snapshot=(),
        created_at=datetime.now(UTC),
    )
    result = SimulatedEmailSender("compras@example.mx").send(message, ())
    assert result.success is True
    assert result.provider_name == "simulation"
    assert result.external_message_id == f"<simulated-{message.idempotency_key}@smartquote.local>"
    assert result.retryable is False
