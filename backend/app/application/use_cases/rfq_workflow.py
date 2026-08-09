import hashlib
import json
import logging
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.application.dtos.rfq_workflow import (
    GenerateRfqCommand,
    RfqVersionResponse,
    RfqVersionsResponse,
)
from app.application.dtos.rfqs import CompanyProfile, RfqResponse, UpdateRfqCommand
from app.application.exceptions import TenderNotFound
from app.application.ports.attachment_provider import AttachmentProvider
from app.application.ports.email_composer import EmailComposer
from app.application.ports.email_sender import EmailSender
from app.application.ports.rfq_delivery_queue import RfqDeliveryQueue
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.application.services.rfq_delivery_policy import (
    require_authorized_user,
    validate_products,
    validate_rfq_send,
    validate_supplier_contact,
)
from app.application.use_cases.rfqs import _rfq_response
from app.domain.rfqs.entities import (
    EmailMessage,
    OutboundMessageLog,
    RfqRequest,
    RfqTaskRecord,
    RfqVersionSnapshot,
)
from app.domain.rfqs.events import rfq_event
from app.domain.rfqs.exceptions import (
    AmbiguousEmailDeliveryError,
    DuplicateRfqSend,
    EmailDeliveryError,
    InvalidRfqState,
    RetryableEmailDeliveryError,
    RfqGenerationError,
    RfqNotFound,
)
from app.domain.rfqs.value_objects import EmailMessageStatus, OutboundLogResult, RfqStatus
from app.domain.tenders.value_objects import TenderStatus

logger = logging.getLogger(__name__)


def _hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _product_payload(product) -> dict[str, Any]:
    specifications = dict(product.specifications)
    lowered = {key.casefold(): value for key, value in specifications.items()}
    return {
        "product_id": str(product.id),
        "item_number": product.item_number,
        "name": product.name,
        "description": product.description,
        "quantity": str(product.quantity.value) if product.quantity else None,
        "unit": product.unit,
        "category": product.category,
        "brand": lowered.get("marca") or lowered.get("brand"),
        "model": lowered.get("modelo") or lowered.get("model"),
        "specifications": specifications,
        "observations": product.observations,
    }


def _version_snapshot(
    rfq: RfqRequest,
    attachments,
    user_id: UUID,
    reason: str | None,
) -> RfqVersionSnapshot:
    return RfqVersionSnapshot(
        rfq_id=rfq.id,
        version=rfq.version,
        changed_by_user_id=user_id,
        status=rfq.status,
        contact_id=rfq.contact_id,
        subject=rfq.subject,
        body=rfq.body,
        to_recipients=rfq.to_recipients,
        cc_recipients=rfq.cc_recipients,
        bcc_recipients=rfq.bcc_recipients,
        products=rfq.products,
        attachment_snapshot=tuple(item.snapshot() for item in attachments),
        change_reason=reason,
    )


def _assert_tender_open(tender) -> None:
    if tender is None or tender.is_deleted:
        raise TenderNotFound("Tender was not found.")
    if tender.status in {TenderStatus.CLOSED, TenderStatus.CANCELLED}:
        raise RfqGenerationError("Closed or cancelled tenders cannot generate RFQs.")


class GenerateRfq:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        composer: EmailComposer,
        attachment_provider: AttachmentProvider,
        company: CompanyProfile,
    ) -> None:
        self._uow_factory = uow_factory
        self._composer = composer
        self._attachment_provider = attachment_provider
        self._company = company

    def execute(self, command: GenerateRfqCommand) -> RfqResponse:
        started = time.perf_counter()
        deadline = command.response_deadline
        if deadline.tzinfo is None or deadline.utcoffset() is None:
            raise RfqGenerationError("RFQ response deadline must include a timezone.")
        deadline = deadline.astimezone(UTC)
        if deadline <= datetime.now(UTC):
            raise RfqGenerationError("RFQ response deadline must be in the future.")

        with self._uow_factory() as uow:
            require_authorized_user(uow, command.generated_by_user_id)
            tender = uow.tenders.get_by_id(command.tender_id)
            _assert_tender_open(tender)
            snapshot = uow.catalogs.get_latest_snapshot(command.tender_id)
            if snapshot is None:
                raise RfqGenerationError("RFQ requires an approved catalog snapshot.")
            context = validate_supplier_contact(
                uow,
                tender_id=command.tender_id,
                supplier_id=command.supplier_id,
                contact_id=command.contact_id,
            )
            products = validate_products(uow, command.tender_id, command.product_ids)
            supplier = uow.suppliers.get_supplier(command.supplier_id)
            if supplier is None:
                raise RfqGenerationError("RFQ supplier was not found.")
            product_payloads = tuple(_product_payload(product) for product in products)
            generation_key = _hash(
                {
                    "tender_id": str(command.tender_id),
                    "supplier_id": str(command.supplier_id),
                    "contact_id": str(command.contact_id),
                    "catalog_snapshot_id": str(snapshot.id),
                    "product_ids": sorted(str(value) for value in command.product_ids),
                    "document_ids": sorted(str(value) for value in command.document_ids),
                    "response_deadline": deadline.isoformat(),
                    "template": [command.template_name, command.template_version],
                    "requested_currency": command.requested_currency,
                    "commercial_terms": command.commercial_terms,
                    "quote_validity": command.quote_validity,
                    "response_instructions": command.response_instructions,
                    "observations": command.observations,
                }
            )
            existing = uow.rfqs.get_by_generation_key(command.tender_id, generation_key)
            if existing is not None:
                return _rfq_response(uow, existing)

            rendered = self._composer.compose(
                command.template_name,
                command.template_version,
                {
                    "company": {
                        "name": self._company.name,
                        "contact_name": self._company.contact_name,
                        "email": self._company.email,
                        "phone": self._company.phone,
                    },
                    "tender": {
                        "title": tender.title,
                        "reference": str(tender.id),
                    },
                    "supplier": {"name": supplier.display_name},
                    "contact": {"name": context.contact.contact_name},
                    "products": product_payloads,
                    "response_deadline": deadline.isoformat(),
                    "requested_currency": command.requested_currency,
                    "commercial_terms": command.commercial_terms,
                    "quote_validity": command.quote_validity,
                    "response_instructions": command.response_instructions,
                    "observations": command.observations,
                },
            )
            rfq = RfqRequest(
                tender_id=command.tender_id,
                tender_supplier_id=context.tender_supplier.id,
                supplier_id=command.supplier_id,
                contact_id=command.contact_id,
                catalog_snapshot_id=snapshot.id,
                generated_by_user_id=command.generated_by_user_id,
                response_deadline=deadline,
                template_name=rendered.template_name,
                template_version=rendered.template_version,
                subject=rendered.subject,
                body=rendered.body,
                products=product_payloads,
                generation_key=generation_key,
                generation_duration_ms=round((time.perf_counter() - started) * 1000),
                to_recipients=(context.contact.value,),
                contact_name=context.contact.contact_name,
                observations=command.observations,
            )
            attachments = self._attachment_provider.build_metadata(
                command.tender_id,
                rfq.id,
                command.document_ids,
            )
            uow.rfqs.create_rfq(rfq)
            uow.rfqs.replace_attachments(rfq.id, attachments)
            uow.rfqs.create_version(
                _version_snapshot(rfq, attachments, command.generated_by_user_id, "generated")
            )
            uow.audit_events.append(
                rfq_event(
                    rfq.id,
                    "RfqGenerated",
                    tender_id=str(rfq.tender_id),
                    supplier_id=str(rfq.supplier_id),
                    contact_id=str(rfq.contact_id),
                    version=rfq.version,
                    product_count=len(rfq.products),
                    attachment_count=len(attachments),
                    template_version=rfq.template_version,
                )
            )
            uow.commit()
            return _rfq_response(uow, rfq)


class UpdateRfqWorkflow:
    def __init__(self, uow_factory: UnitOfWorkFactory, attachment_provider: AttachmentProvider) -> None:
        self._uow_factory = uow_factory
        self._attachment_provider = attachment_provider

    def execute(
        self,
        rfq_id: UUID,
        command: UpdateRfqCommand,
        *,
        change_reason: str | None = None,
    ) -> RfqResponse:
        with self._uow_factory() as uow:
            require_authorized_user(uow, command.changed_by_user_id)
            rfq = uow.rfqs.get_rfq(rfq_id, for_update=True)
            if rfq is None:
                raise RfqNotFound("RFQ was not found.")
            if command.to_recipients is not None or command.cc_recipients or command.bcc_recipients:
                raise InvalidRfqState(
                    "The reviewed contact controls RFQ recipients; select a new contact by regenerating."
                )
            before_version = rfq.version
            rfq.edit(
                subject=command.subject,
                body=command.body,
                response_deadline=command.response_deadline,
                observations=command.observations,
                contact_name=command.contact_name,
            )
            attachments = tuple(uow.rfqs.list_attachments(rfq.id))
            if command.document_ids is not None:
                updated_attachments = self._attachment_provider.build_metadata(
                    rfq.tender_id,
                    rfq.id,
                    command.document_ids,
                )
                if tuple(item.document_id for item in updated_attachments) != tuple(
                    item.document_id for item in attachments
                ):
                    if rfq.version == before_version:
                        rfq.record_attachment_edit()
                    attachments = updated_attachments
                    uow.rfqs.replace_attachments(rfq.id, attachments)
            if rfq.version == before_version:
                return _rfq_response(uow, rfq)
            uow.rfqs.update_rfq(rfq)
            uow.rfqs.create_version(
                _version_snapshot(
                    rfq,
                    attachments,
                    command.changed_by_user_id,
                    change_reason or "edited",
                )
            )
            uow.audit_events.append(
                rfq_event(
                    rfq.id,
                    "RfqEdited",
                    version=rfq.version,
                    changed_by_user_id=str(command.changed_by_user_id),
                    change_reason=change_reason,
                )
            )
            uow.commit()
            return _rfq_response(uow, rfq)


class SubmitRfqForReview:
    def __init__(self, uow_factory: UnitOfWorkFactory, attachment_provider: AttachmentProvider) -> None:
        self._uow_factory = uow_factory
        self._attachment_provider = attachment_provider

    def execute(self, rfq_id: UUID, user_id: UUID) -> RfqResponse:
        with self._uow_factory() as uow:
            require_authorized_user(uow, user_id)
            rfq = uow.rfqs.get_rfq(rfq_id, for_update=True)
            if rfq is None:
                raise RfqNotFound("RFQ was not found.")
            if rfq.status is not RfqStatus.DRAFT:
                raise InvalidRfqState("Only draft RFQs can be submitted for review.")
            if rfq.contact_id is None:
                raise InvalidRfqState("RFQ requires a selected contact before review.")
            validate_supplier_contact(
                uow,
                tender_id=rfq.tender_id,
                supplier_id=rfq.supplier_id,
                contact_id=rfq.contact_id,
            )
            product_ids = tuple(UUID(str(item["product_id"])) for item in rfq.products)
            validate_products(uow, rfq.tender_id, product_ids)
            attachments = tuple(uow.rfqs.list_attachments(rfq.id))
            if attachments:
                self._attachment_provider.load(attachments)
            rfq.start_review()
            uow.rfqs.update_rfq(rfq)
            uow.audit_events.append(
                rfq_event(
                    rfq.id,
                    "RfqReviewed",
                    decision="submitted",
                    reviewed_by_user_id=str(user_id),
                    version=rfq.version,
                )
            )
            uow.commit()
            return _rfq_response(uow, rfq)


class ApproveRfqWorkflow:
    def __init__(self, uow_factory: UnitOfWorkFactory, attachment_provider: AttachmentProvider) -> None:
        self._uow_factory = uow_factory
        self._attachment_provider = attachment_provider

    def execute(self, rfq_id: UUID, user_id: UUID) -> RfqResponse:
        with self._uow_factory() as uow:
            require_authorized_user(uow, user_id)
            rfq = uow.rfqs.get_rfq(rfq_id, for_update=True)
            if rfq is None:
                raise RfqNotFound("RFQ was not found.")
            if rfq.status is not RfqStatus.PENDING_REVIEW:
                raise InvalidRfqState("Only pending-review RFQs can be approved.")
            if rfq.contact_id is None:
                raise InvalidRfqState("RFQ requires a selected contact before approval.")
            validate_supplier_contact(
                uow,
                tender_id=rfq.tender_id,
                supplier_id=rfq.supplier_id,
                contact_id=rfq.contact_id,
            )
            product_ids = tuple(UUID(str(item["product_id"])) for item in rfq.products)
            validate_products(uow, rfq.tender_id, product_ids)
            attachments = tuple(uow.rfqs.list_attachments(rfq.id))
            if attachments:
                self._attachment_provider.load(attachments)
            rfq.approve(user_id, attachments)
            uow.rfqs.update_rfq(rfq)
            uow.audit_events.append(
                rfq_event(
                    rfq.id,
                    "RfqApproved",
                    approved_by_user_id=str(user_id),
                    version=rfq.version,
                )
            )
            uow.commit()
            return _rfq_response(uow, rfq)


class RejectRfq:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, rfq_id: UUID, user_id: UUID, reason: str) -> RfqResponse:
        if not reason.strip():
            raise InvalidRfqState("RFQ review rejection requires a reason.")
        with self._uow_factory() as uow:
            require_authorized_user(uow, user_id)
            rfq = uow.rfqs.get_rfq(rfq_id, for_update=True)
            if rfq is None:
                raise RfqNotFound("RFQ was not found.")
            if rfq.status is not RfqStatus.PENDING_REVIEW:
                raise InvalidRfqState("Only pending-review RFQs can be rejected for changes.")
            rfq.reject_review()
            uow.rfqs.update_rfq(rfq)
            uow.audit_events.append(
                rfq_event(
                    rfq.id,
                    "RfqReviewed",
                    decision="rejected",
                    reviewed_by_user_id=str(user_id),
                    reason=reason[:2000],
                    version=rfq.version,
                )
            )
            uow.commit()
            return _rfq_response(uow, rfq)


class QueueRfq:
    def __init__(self, uow_factory: UnitOfWorkFactory, queue: RfqDeliveryQueue) -> None:
        self._uow_factory = uow_factory
        self._queue = queue

    def execute(self, rfq_id: UUID, user_id: UUID) -> RfqResponse:
        correlation_id = str(uuid4())
        with self._uow_factory() as uow:
            rfq = uow.rfqs.get_rfq(rfq_id, for_update=True)
            if rfq is None:
                raise RfqNotFound("RFQ was not found.")
            validate_rfq_send(uow, rfq, user_id)
            existing = (
                uow.rfqs.get_message_by_idempotency(rfq.send_idempotency_key)
                if rfq.send_idempotency_key
                else None
            )
            if existing is not None and existing.status is EmailMessageStatus.SENT:
                raise DuplicateRfqSend("This exact RFQ version was already sent.")
            if rfq.status is not RfqStatus.APPROVED:
                raise InvalidRfqState("Only approved RFQs can be queued from the API.")
            rfq.queue(user_id)
            task = RfqTaskRecord(rfq_id=rfq.id, correlation_id=correlation_id)
            uow.rfqs.update_rfq(rfq)
            uow.rfqs.create_task(task)
            uow.audit_events.append(
                rfq_event(
                    rfq.id,
                    "RfqQueued",
                    requested_by_user_id=str(user_id),
                    correlation_id=correlation_id,
                    task_record_id=str(task.id),
                    version=rfq.version,
                )
            )
            uow.commit()
        try:
            self._queue.enqueue(
                rfq_id,
                task_record_id=task.id,
                correlation_id=correlation_id,
            )
        except Exception as exc:
            with self._uow_factory() as uow:
                failed = uow.rfqs.get_rfq(rfq_id, for_update=True)
                task_record = uow.rfqs.get_task(task.id, for_update=True)
                if failed is not None and failed.status is RfqStatus.QUEUED:
                    failed.mark_failed("RFQ delivery queue is unavailable.")
                    uow.rfqs.update_rfq(failed)
                if task_record is not None:
                    task_record.fail("RFQ delivery queue is unavailable.")
                    uow.rfqs.update_task(task_record)
                uow.audit_events.append(
                    rfq_event(
                        rfq_id,
                        "RfqFailed",
                        stage="queue",
                        error_type=type(exc).__name__,
                        correlation_id=correlation_id,
                    )
                )
                uow.commit()
            raise EmailDeliveryError("RFQ delivery queue is unavailable.") from exc
        with self._uow_factory() as uow:
            current = uow.rfqs.get_rfq(rfq_id)
            if current is None:
                raise RfqNotFound("RFQ was not found after queueing.")
            return _rfq_response(uow, current)


class RetryFailedRfq:
    def __init__(self, uow_factory: UnitOfWorkFactory, queue: RfqDeliveryQueue) -> None:
        self._uow_factory = uow_factory
        self._queue = queue

    def execute(self, rfq_id: UUID, user_id: UUID) -> RfqResponse:
        correlation_id = str(uuid4())
        with self._uow_factory() as uow:
            require_authorized_user(uow, user_id)
            rfq = uow.rfqs.get_rfq(rfq_id, for_update=True)
            if rfq is None:
                raise RfqNotFound("RFQ was not found.")
            if rfq.status not in {RfqStatus.FAILED, RfqStatus.RETRY_PENDING}:
                raise InvalidRfqState("Only failed or retry-pending RFQs can be retried.")
            messages = uow.rfqs.list_messages(rfq.id)
            if messages and messages[-1].error_type == "AmbiguousEmailDeliveryError":
                raise InvalidRfqState(
                    "Delivery outcome is ambiguous; verify provider state before another send."
                )
            validate_rfq_send(uow, rfq, user_id)
            if rfq.status is RfqStatus.FAILED:
                rfq.mark_retry_pending(rfq.last_error)
            rfq.queue(user_id)
            task = RfqTaskRecord(rfq_id=rfq.id, correlation_id=correlation_id)
            uow.rfqs.update_rfq(rfq)
            uow.rfqs.create_task(task)
            uow.audit_events.append(
                rfq_event(
                    rfq.id,
                    "RfqQueued",
                    requested_by_user_id=str(user_id),
                    retry=True,
                    correlation_id=correlation_id,
                    task_record_id=str(task.id),
                    version=rfq.version,
                )
            )
            uow.commit()
        self._queue.enqueue(
            rfq_id,
            task_record_id=task.id,
            correlation_id=correlation_id,
        )
        with self._uow_factory() as uow:
            current = uow.rfqs.get_rfq(rfq_id)
            if current is None:
                raise RfqNotFound("RFQ was not found after retry queueing.")
            return _rfq_response(uow, current)


class SendRfq:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        attachment_provider: AttachmentProvider,
        email_sender: EmailSender,
    ) -> None:
        self._uow_factory = uow_factory
        self._attachment_provider = attachment_provider
        self._email_sender = email_sender

    def execute(
        self,
        rfq_id: UUID,
        task_record_id: UUID | None = None,
        correlation_id: str | None = None,
    ) -> UUID:
        with self._uow_factory() as uow:
            rfq = uow.rfqs.get_rfq(rfq_id, for_update=True)
            if rfq is None:
                raise RfqNotFound("RFQ was not found.")
            user_id = rfq.send_requested_by_user_id
            if user_id is None:
                raise InvalidRfqState("RFQ has no explicit send approval action.")
            validate_rfq_send(uow, rfq, user_id)
            if not rfq.send_idempotency_key:
                raise InvalidRfqState("RFQ has no approved send idempotency key.")
            existing = uow.rfqs.get_message_by_idempotency(rfq.send_idempotency_key)
            if existing is not None and existing.status is EmailMessageStatus.SENT:
                task = (
                    uow.rfqs.get_task(task_record_id, for_update=True)
                    if task_record_id
                    else None
                )
                if task is not None:
                    task.succeed()
                    uow.rfqs.update_task(task)
                    uow.commit()
                return existing.id
            if existing is not None and existing.status is EmailMessageStatus.SENDING:
                return existing.id
            if existing is not None and existing.error_type == "AmbiguousEmailDeliveryError":
                raise AmbiguousEmailDeliveryError(
                    "Previous delivery outcome is ambiguous; automatic retry is blocked."
                )
            attachments = tuple(uow.rfqs.list_attachments(rfq.id))
            task = (
                uow.rfqs.get_task(task_record_id, for_update=True)
                if task_record_id
                else None
            )
            if task is not None:
                task.start()
                uow.rfqs.update_task(task)
            if rfq.status is RfqStatus.RETRY_PENDING:
                rfq.queue(user_id)
            if rfq.status is not RfqStatus.QUEUED:
                raise InvalidRfqState("Only queued RFQs can start delivery.")
            rfq.start_sending()
            if existing is None:
                message = EmailMessage(
                    rfq_id=rfq.id,
                    rfq_version=rfq.version,
                    attempt_number=uow.rfqs.next_attempt_number(rfq.id),
                    idempotency_key=rfq.send_idempotency_key,
                    provider_name=self._email_sender.provider_name,
                    from_address=self._email_sender.sender_address,
                    to_recipients=rfq.to_recipients,
                    cc_recipients=rfq.cc_recipients,
                    bcc_recipients=rfq.bcc_recipients,
                    subject=rfq.subject,
                    body=rfq.body,
                    attachment_snapshot=tuple(item.snapshot() for item in attachments),
                )
                message.start()
                uow.rfqs.create_message(message)
            else:
                message = existing
                message.status = EmailMessageStatus.QUEUED
                message.error_type = None
                message.error_message = None
                message.failed_at = None
                message.start()
                uow.rfqs.update_message(message)
            uow.rfqs.update_rfq(rfq)
            uow.audit_events.append(
                rfq_event(
                    rfq.id,
                    "EmailSendingStarted",
                    message_id=str(message.id),
                    provider=self._email_sender.provider_name,
                    correlation_id=correlation_id,
                )
            )
            uow.commit()

        started = time.perf_counter()
        try:
            content = self._attachment_provider.load(attachments)
            result = self._email_sender.send(message, content)
            if not result.success:
                if result.retryable:
                    raise RetryableEmailDeliveryError(result.error or "Email provider failed.")
                raise EmailDeliveryError(result.error or "Email provider failed.")
        except Exception as exc:
            duration_ms = round((time.perf_counter() - started) * 1000)
            with self._uow_factory() as uow:
                failed_rfq = uow.rfqs.get_rfq(rfq_id, for_update=True)
                failed_message = uow.rfqs.get_message(message.id, for_update=True)
                task = (
                    uow.rfqs.get_task(task_record_id, for_update=True)
                    if task_record_id
                    else None
                )
                if failed_rfq is not None and failed_message is not None:
                    failed_message.fail(exc, duration_ms)
                    uow.rfqs.update_message(failed_message)
                    if isinstance(exc, RetryableEmailDeliveryError):
                        failed_rfq.mark_retry_pending(str(exc))
                        if task is not None:
                            task.retry(str(exc))
                    else:
                        failed_rfq.mark_failed(str(exc))
                        if task is not None:
                            task.fail(str(exc))
                    uow.rfqs.update_rfq(failed_rfq)
                    if task is not None:
                        uow.rfqs.update_task(task)
                    uow.rfqs.add_log(
                        OutboundMessageLog(
                            rfq_id=failed_rfq.id,
                            email_message_id=failed_message.id,
                            event_type="RfqFailed",
                            result=OutboundLogResult.FAILURE,
                            provider_name=self._email_sender.provider_name,
                            details={
                                "error_type": type(exc).__name__,
                                "duration_ms": duration_ms,
                                "retryable": isinstance(exc, RetryableEmailDeliveryError),
                                "correlation_id": correlation_id,
                            },
                        )
                    )
                    uow.audit_events.append(
                        rfq_event(
                            failed_rfq.id,
                            "RfqFailed",
                            error_type=type(exc).__name__,
                            retryable=isinstance(exc, RetryableEmailDeliveryError),
                            correlation_id=correlation_id,
                        )
                    )
                    uow.commit()
            if isinstance(exc, EmailDeliveryError):
                raise
            raise EmailDeliveryError("RFQ email delivery failed.") from exc

        with self._uow_factory() as uow:
            sent_rfq = uow.rfqs.get_rfq(rfq_id, for_update=True)
            sent_message = uow.rfqs.get_message(message.id, for_update=True)
            task = (
                uow.rfqs.get_task(task_record_id, for_update=True)
                if task_record_id
                else None
            )
            if sent_rfq is None or sent_message is None:
                raise RfqNotFound("RFQ delivery state was not found.")
            sent_message.succeed(result.external_message_id, result.duration_ms)
            sent_rfq.mark_sent()
            uow.rfqs.update_message(sent_message)
            uow.rfqs.update_rfq(sent_rfq)
            if task is not None:
                task.succeed()
                uow.rfqs.update_task(task)
            uow.rfqs.add_log(
                OutboundMessageLog(
                    rfq_id=sent_rfq.id,
                    email_message_id=sent_message.id,
                    event_type="RfqSent",
                    result=OutboundLogResult.SUCCESS,
                    provider_name=result.provider_name,
                    details={
                        "external_message_id": result.external_message_id,
                        "duration_ms": result.duration_ms,
                        "correlation_id": correlation_id,
                    },
                )
            )
            uow.audit_events.append(
                rfq_event(
                    sent_rfq.id,
                    "RfqSent",
                    message_id=str(sent_message.id),
                    provider=result.provider_name,
                    external_message_id=result.external_message_id,
                    duration_ms=result.duration_ms,
                    correlation_id=correlation_id,
                )
            )
            uow.commit()
            logger.info(
                "rfq_sent",
                extra={
                    "rfq_id": str(sent_rfq.id),
                    "message_id": str(sent_message.id),
                    "provider": result.provider_name,
                    "duration_ms": result.duration_ms,
                    "correlation_id": correlation_id,
                },
            )
            return sent_message.id


class GetRfqVersions:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, rfq_id: UUID) -> RfqVersionsResponse:
        with self._uow_factory() as uow:
            if uow.rfqs.get_rfq(rfq_id) is None:
                raise RfqNotFound("RFQ was not found.")
            versions = tuple(
                RfqVersionResponse(
                    id=item.id,
                    rfq_id=item.rfq_id,
                    version=item.version,
                    changed_by_user_id=item.changed_by_user_id,
                    status=item.status,
                    contact_id=item.contact_id,
                    subject=item.subject,
                    body=item.body,
                    to_recipients=item.to_recipients,
                    cc_recipients=item.cc_recipients,
                    bcc_recipients=item.bcc_recipients,
                    products=item.products,
                    attachment_snapshot=item.attachment_snapshot,
                    change_reason=item.change_reason,
                    created_at=item.created_at,
                )
                for item in uow.rfqs.list_versions(rfq_id)
            )
        return RfqVersionsResponse(rfq_id=rfq_id, versions=versions)
