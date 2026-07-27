from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.application.ports.attachment_provider import AttachmentContent
from app.domain.rfqs.entities import EmailMessage


@dataclass(frozen=True, slots=True)
class EmailSendResult:
    provider_name: str
    external_message_id: str
    duration_ms: int


class EmailSender(ABC):
    provider_name: str
    sender_address: str

    @abstractmethod
    def send(
        self,
        message: EmailMessage,
        attachments: tuple[AttachmentContent, ...],
    ) -> EmailSendResult: ...
