from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.rfqs.entities import (
    EmailAttachment,
    EmailMessage,
    OutboundMessageLog,
    RfqRequest,
)


class RfqRepository(ABC):
    @abstractmethod
    def create_rfq(self, rfq: RfqRequest) -> RfqRequest: ...

    @abstractmethod
    def update_rfq(self, rfq: RfqRequest) -> RfqRequest: ...

    @abstractmethod
    def get_rfq(self, rfq_id: UUID, *, for_update: bool = False) -> RfqRequest | None: ...

    @abstractmethod
    def get_by_generation_key(self, tender_id: UUID, key: str) -> RfqRequest | None: ...

    @abstractmethod
    def list_rfqs(self, tender_id: UUID) -> list[RfqRequest]: ...

    @abstractmethod
    def replace_attachments(
        self, rfq_id: UUID, attachments: tuple[EmailAttachment, ...]
    ) -> tuple[EmailAttachment, ...]: ...

    @abstractmethod
    def list_attachments(self, rfq_id: UUID) -> list[EmailAttachment]: ...

    @abstractmethod
    def create_message(self, message: EmailMessage) -> EmailMessage: ...

    @abstractmethod
    def update_message(self, message: EmailMessage) -> EmailMessage: ...

    @abstractmethod
    def get_message(
        self, message_id: UUID, *, for_update: bool = False
    ) -> EmailMessage | None: ...

    @abstractmethod
    def list_messages(self, rfq_id: UUID) -> list[EmailMessage]: ...

    @abstractmethod
    def get_sent_message(self, rfq_id: UUID, rfq_version: int) -> EmailMessage | None: ...

    @abstractmethod
    def next_attempt_number(self, rfq_id: UUID) -> int: ...

    @abstractmethod
    def add_log(self, log: OutboundMessageLog) -> OutboundMessageLog: ...

    @abstractmethod
    def list_logs(self, rfq_id: UUID) -> list[OutboundMessageLog]: ...
