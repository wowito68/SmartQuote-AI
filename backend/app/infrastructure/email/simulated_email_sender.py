import time

from app.application.ports.attachment_provider import AttachmentContent
from app.application.ports.email_sender import EmailSender, EmailSendResult
from app.domain.rfqs.entities import EmailMessage


class SimulatedEmailSender(EmailSender):
    """Non-network email adapter for development, CI and deterministic tests."""

    provider_name = "simulation"

    def __init__(self, sender_address: str = "procurement@smartquote.local") -> None:
        self.sender_address = sender_address

    def send(
        self,
        message: EmailMessage,
        attachments: tuple[AttachmentContent, ...],
    ) -> EmailSendResult:
        del attachments
        started = time.perf_counter()
        external_message_id = f"<simulated-{message.idempotency_key}@smartquote.local>"
        return EmailSendResult(
            provider_name=self.provider_name,
            external_message_id=external_message_id,
            duration_ms=round((time.perf_counter() - started) * 1000),
        )
