from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.application.ports.rfq_repository import RfqRepository
from app.domain.rfqs.entities import (
    EmailAttachment,
    EmailMessage,
    OutboundMessageLog,
    RfqRequest,
    RfqTaskRecord,
    RfqVersionSnapshot,
)
from app.infrastructure.db.mappers.rfq_mapper import (
    attachment_to_domain,
    attachment_to_model,
    log_to_domain,
    log_to_model,
    message_to_domain,
    message_to_model,
    rfq_to_domain,
    rfq_to_model,
    task_to_domain,
    task_to_model,
    update_message_model,
    update_rfq_model,
    update_task_model,
    version_to_domain,
    version_to_model,
)
from app.infrastructure.db.models.rfq import (
    EmailAttachmentModel,
    EmailMessageModel,
    OutboundMessageLogModel,
    RfqRequestModel,
    RfqTaskRecordModel,
    RfqVersionModel,
)


class SqlAlchemyRfqRepository(RfqRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_rfq(self, rfq: RfqRequest) -> RfqRequest:
        model = rfq_to_model(rfq)
        self._session.add(model)
        self._session.flush()
        return rfq_to_domain(model)

    def update_rfq(self, rfq: RfqRequest) -> RfqRequest:
        model = self._session.get(RfqRequestModel, rfq.id)
        if model is None:
            raise ValueError("RFQ does not exist.")
        update_rfq_model(model, rfq)
        self._session.flush()
        return rfq_to_domain(model)

    def get_rfq(self, rfq_id: UUID, *, for_update: bool = False) -> RfqRequest | None:
        statement = select(RfqRequestModel).where(RfqRequestModel.id == rfq_id)
        if for_update:
            statement = statement.with_for_update()
        model = self._session.scalars(statement).first()
        return rfq_to_domain(model) if model else None

    def get_by_generation_key(self, tender_id: UUID, key: str) -> RfqRequest | None:
        statement = select(RfqRequestModel).where(
            RfqRequestModel.tender_id == tender_id,
            RfqRequestModel.generation_key == key,
        )
        model = self._session.scalars(statement).first()
        return rfq_to_domain(model) if model else None

    def list_rfqs(self, tender_id: UUID) -> list[RfqRequest]:
        statement = (
            select(RfqRequestModel)
            .where(RfqRequestModel.tender_id == tender_id)
            .order_by(RfqRequestModel.created_at, RfqRequestModel.id)
        )
        return [rfq_to_domain(model) for model in self._session.scalars(statement)]

    def create_version(self, version: RfqVersionSnapshot) -> RfqVersionSnapshot:
        model = version_to_model(version)
        self._session.add(model)
        self._session.flush()
        return version_to_domain(model)

    def list_versions(self, rfq_id: UUID) -> list[RfqVersionSnapshot]:
        statement = (
            select(RfqVersionModel)
            .where(RfqVersionModel.rfq_id == rfq_id)
            .order_by(RfqVersionModel.version)
        )
        return [version_to_domain(model) for model in self._session.scalars(statement)]

    def replace_attachments(
        self, rfq_id: UUID, attachments: tuple[EmailAttachment, ...]
    ) -> tuple[EmailAttachment, ...]:
        self._session.execute(
            delete(EmailAttachmentModel).where(EmailAttachmentModel.rfq_id == rfq_id)
        )
        models = [attachment_to_model(item) for item in attachments]
        self._session.add_all(models)
        self._session.flush()
        return tuple(attachment_to_domain(model) for model in models)

    def list_attachments(self, rfq_id: UUID) -> list[EmailAttachment]:
        statement = (
            select(EmailAttachmentModel)
            .where(EmailAttachmentModel.rfq_id == rfq_id)
            .order_by(EmailAttachmentModel.created_at, EmailAttachmentModel.id)
        )
        return [attachment_to_domain(model) for model in self._session.scalars(statement)]

    def create_message(self, message: EmailMessage) -> EmailMessage:
        model = message_to_model(message)
        self._session.add(model)
        self._session.flush()
        return message_to_domain(model)

    def update_message(self, message: EmailMessage) -> EmailMessage:
        model = self._session.get(EmailMessageModel, message.id)
        if model is None:
            raise ValueError("Email message does not exist.")
        update_message_model(model, message)
        self._session.flush()
        return message_to_domain(model)

    def get_message(
        self, message_id: UUID, *, for_update: bool = False
    ) -> EmailMessage | None:
        statement = select(EmailMessageModel).where(EmailMessageModel.id == message_id)
        if for_update:
            statement = statement.with_for_update()
        model = self._session.scalars(statement).first()
        return message_to_domain(model) if model else None

    def get_message_by_idempotency(self, key: str) -> EmailMessage | None:
        model = self._session.scalars(
            select(EmailMessageModel).where(EmailMessageModel.idempotency_key == key)
        ).first()
        return message_to_domain(model) if model else None

    def list_messages(self, rfq_id: UUID) -> list[EmailMessage]:
        statement = (
            select(EmailMessageModel)
            .where(EmailMessageModel.rfq_id == rfq_id)
            .order_by(EmailMessageModel.attempt_number)
        )
        return [message_to_domain(model) for model in self._session.scalars(statement)]

    def get_sent_message(self, rfq_id: UUID, rfq_version: int) -> EmailMessage | None:
        statement = select(EmailMessageModel).where(
            EmailMessageModel.rfq_id == rfq_id,
            EmailMessageModel.rfq_version == rfq_version,
            EmailMessageModel.status == "sent",
        )
        model = self._session.scalars(statement).first()
        return message_to_domain(model) if model else None

    def next_attempt_number(self, rfq_id: UUID) -> int:
        maximum = self._session.scalar(
            select(func.max(EmailMessageModel.attempt_number)).where(
                EmailMessageModel.rfq_id == rfq_id
            )
        )
        return int(maximum or 0) + 1

    def create_task(self, task: RfqTaskRecord) -> RfqTaskRecord:
        model = task_to_model(task)
        self._session.add(model)
        self._session.flush()
        return task_to_domain(model)

    def update_task(self, task: RfqTaskRecord) -> RfqTaskRecord:
        model = self._session.get(RfqTaskRecordModel, task.id)
        if model is None:
            raise ValueError("RFQ task record does not exist.")
        update_task_model(model, task)
        self._session.flush()
        return task_to_domain(model)

    def get_task(self, task_id: UUID, *, for_update: bool = False) -> RfqTaskRecord | None:
        statement = select(RfqTaskRecordModel).where(RfqTaskRecordModel.id == task_id)
        if for_update:
            statement = statement.with_for_update()
        model = self._session.scalars(statement).first()
        return task_to_domain(model) if model else None

    def get_task_by_correlation(self, correlation_id: str) -> RfqTaskRecord | None:
        model = self._session.scalars(
            select(RfqTaskRecordModel).where(
                RfqTaskRecordModel.correlation_id == correlation_id
            )
        ).first()
        return task_to_domain(model) if model else None

    def list_tasks(self, rfq_id: UUID) -> list[RfqTaskRecord]:
        statement = (
            select(RfqTaskRecordModel)
            .where(RfqTaskRecordModel.rfq_id == rfq_id)
            .order_by(RfqTaskRecordModel.queued_at, RfqTaskRecordModel.id)
        )
        return [task_to_domain(model) for model in self._session.scalars(statement)]

    def add_log(self, log: OutboundMessageLog) -> OutboundMessageLog:
        model = log_to_model(log)
        self._session.add(model)
        self._session.flush()
        return log_to_domain(model)

    def list_logs(self, rfq_id: UUID) -> list[OutboundMessageLog]:
        statement = (
            select(OutboundMessageLogModel)
            .where(OutboundMessageLogModel.rfq_id == rfq_id)
            .order_by(OutboundMessageLogModel.occurred_at, OutboundMessageLogModel.id)
        )
        return [log_to_domain(model) for model in self._session.scalars(statement)]
