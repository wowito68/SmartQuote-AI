from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID

from app.domain.rfqs.entities import EmailAttachment


@dataclass(frozen=True, slots=True)
class AttachmentContent:
    metadata: EmailAttachment
    content: bytes


class AttachmentProvider(ABC):
    @abstractmethod
    def build_metadata(
        self,
        tender_id: UUID,
        rfq_id: UUID,
        document_ids: tuple[UUID, ...] | None,
    ) -> tuple[EmailAttachment, ...]: ...

    @abstractmethod
    def load(self, attachments: tuple[EmailAttachment, ...]) -> tuple[AttachmentContent, ...]: ...
