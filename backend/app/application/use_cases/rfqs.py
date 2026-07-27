import hashlib
import json
import logging
import time
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from app.application.dtos.rfqs import (
    CompanyProfile,
    EmailMessageResponse,
    GenerateRfqsCommand,
    OutboundLogResponse,
    RfqAttachmentResponse,
    RfqGenerationResponse,
    RfqMessagesResponse,
    RfqMetricsResponse,
    RfqResponse,
    TenderRfqsResponse,
    UpdateRfqCommand,
)
from app.application.ports.attachment_provider import AttachmentProvider
from app.application.ports.email_composer import EmailComposer
from app.application.ports.email_sender import EmailSender
from app.application.ports.rfq_delivery_queue import RfqDeliveryQueue
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.domain.rfqs.entities import EmailMessage, OutboundMessageLog, RfqRequest
from app.domain.rfqs.events import rfq_event
from app.domain.rfqs.exceptions import (
    DuplicateRfqSend,
    EmailDeliveryError,
    InvalidRfqState,
    RfqGenerationError,
    RfqNotFound,
)
from app.domain.rfqs.value_objects import OutboundLogResult, RfqStatus
from app.domain.suppliers.value_objects import SupplierContactType, SupplierStatus
from app.application.exceptions import TenderNotFound

logger = logging.getLogger(__name__)


def _generation_key(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _attachment_response(item) -> RfqAttachmentResponse:
    return RfqAttachmentResponse(
        id=item.id,
        document_id=item.document_id,
        original_file_name=item.original_file_name,
        file_hash=item.file_hash,
        file_size=item.file_size,
        mime_type=item.mime_type,
    )


def _rfq_response(uow, rfq: RfqRequest) -> RfqResponse:
    attachments = tuple(
        _attachment_response(item) for item in uow.rfqs.list_attachments(rfq.id)
    )
    return RfqResponse(
        id=rfq.id,
        tender_id=rfq.tender_id,
        tender_supplier_id=rfq.tender_supplier_id,
        supplier_id=rfq.supplier_id,
        catalog_snapshot_id=rfq.catalog_snapshot_id,
        status=rfq.status,
        version=rfq.version,
        generation_duration_ms=rfq.generation_duration_ms,
        template_name=rfq.template_name,
        template_version=rfq.template_version,
        subject=rfq.subject,
        body=rfq.body,
        products=rfq.products,
        to_recipients=rfq.to_recipients,
        cc_recipients=rfq.cc_recipients,
        bcc_recipients=rfq.bcc_recipients,
        contact_name=rfq.contact_name,
        response_deadline=rfq.response_deadline,
        observations=rfq.observations,
        generated_by_user_id=rfq.generated_by_user_id,
        approved_by_user_id=rfq.approved_by_user_id,
        approved_at=rfq.approved_at,
        send_requested_by_user_id=rfq.send_requested_by_user_id,
        queued_at=rfq.queued_at,
        sending_started_at=rfq.sending_started_at,
        sent_at=rfq.sent_at,
        delivered_at=rfq.delivered_at,
        cancelled_by_user_id=rfq.cancelled_by_user_id,
        cancelled_at=rfq.cancelled_at,
        cancellation_reason=rfq.cancellation_reason,
        last_error=rfq.last_error,
        send_idempotency_key=rfq.send_idempotency_key,
        attachments=attachments,
        created_at=rfq.created_at,
        updated_at=rfq.updated_at,
    )


def _message_response(item: EmailMessage) -> EmailMessageResponse:
    return EmailMessageResponse(
        id=item.id,
        rfq_id=item.rfq_id,
        rfq_version=item.rfq_version,
        attempt_number=item.attempt_number,
        idempotency_key=item.idempotency_key,
        provider_name=item.provider_name,
        from_address=item.from_address,
        to_recipients=item.to_recipients,
        cc_recipients=item.cc_recipients,
        bcc_recipients=item.bcc_recipients,
        subject=item.subject,
        status=item.status,
        attachment_snapshot=item.attachment_snapshot,
        external_message_id=item.external_message_id,
        error_type=item.error_type,
        error_message=item.error_message,
        started_at=item.started_at,
        sent_at=item.sent_at,
        duration_ms=item.duration_ms,
        created_at=item.created_at,
    )


class GenerateTenderRfqs:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        email_composer: EmailComposer,
        attachment_provider: AttachmentProvider,
        company: CompanyProfile,
    ) -> None:
        self._uow_factory = uow_factory
        self._email_composer = email_composer
        self._attachment_provider = attachment_provider
        self._company = company

    def execute(self, command: GenerateRfqsCommand) -> RfqGenerationResponse:
        started = time.perf_counter()
        generated: list[RfqResponse] = []
        reused: list[RfqResponse] = []
        suppliers_without_email: list[UUID] = []
        with self._uow_factory() as uow:
            tender = uow.tenders.get_by_id(command.tender_id)
            if tender is None:
                raise TenderNotFound("Tender was not found.")
            if tender.is_deleted:
                raise RfqGenerationError("Archived tenders cannot generate RFQs.")
            if not uow.users.exists(command.generated_by_user_id):
                raise RfqGenerationError("RFQ generator user does not exist.")
            snapshot = uow.catalogs.get_latest_snapshot(command.tender_id)
            if snapshot is None:
                raise RfqGenerationError("Tender requires an approved catalog snapshot.")
            approved_suppliers = [
                item
                for item in uow.suppliers.list_tender_suppliers(command.tender_id)
                if item.status is SupplierStatus.APPROVED
            ]
            if not approved_suppliers:
                raise RfqGenerationError("Tender has no approved suppliers.")

            snapshot_by_id = {
                str(product.get("product_id")): product for product in snapshot.products
            }
            for tender_supplier in approved_suppliers:
                supplier = uow.suppliers.get_supplier(tender_supplier.supplier_id)
                if supplier is None or supplier.merged_into_supplier_id is not None:
                    continue
                contacts = uow.suppliers.list_contacts(supplier.id)
                email_contacts = sorted(
                    (
                        contact
                        for contact in contacts
                        if contact.contact_type is SupplierContactType.EMAIL
                    ),
                    key=lambda contact: contact.confidence.value,
                    reverse=True,
                )
                recipients = tuple(dict.fromkeys(contact.value for contact in email_contacts))
                if not recipients:
                    suppliers_without_email.append(tender_supplier.id)
                contact_name = next(
                    (contact.contact_name for contact in email_contacts if contact.contact_name),
                    None,
                )
                matches = uow.suppliers.list_matches(tender_supplier.id)
                matched_products = tuple(
                    snapshot_by_id[str(match.product_id)]
                    for match in matches
                    if str(match.product_id) in snapshot_by_id
                )
                products = matched_products or snapshot.products
                candidate_id = uuid4()
                attachments = self._attachment_provider.build_metadata(
                    command.tender_id,
                    candidate_id,
                    command.document_ids,
                )
                key = _generation_key(
                    {
                        "tender_id": str(command.tender_id),
                        "tender_supplier_id": str(tender_supplier.id),
                        "catalog_snapshot_id": str(snapshot.id),
                        "catalog_snapshot_version": snapshot.version,
                        "template_name": command.template_name,
                        "template_version": command.template_version,
                        "response_deadline": command.response_deadline.isoformat(),
                        "observations": command.observations,
                        "products": products,
                        "attachments": [
                            {
                                "document_id": str(item.document_id),
                                "hash": item.file_hash,
                            }
                            for item in attachments
                        ],
                    }
                )
                existing = uow.rfqs.get_by_generation_key(command.tender_id, key)
                if existing is not None:
                    reused.append(_rfq_response(uow, existing))
                    continue
                context = {
                    "company": {
                        "name": self._company.name,
                        "contact_name": self._company.contact_name,
                        "email": self._company.email,
                        "phone": self._company.phone,
                    },
                    "supplier": {"name": supplier.display_name},
                    "contact": {"name": contact_name},
                    "tender": {"id": str(tender.id), "title": tender.title},
                    "products": products,
                    "response_deadline": command.response_deadline.date().isoformat(),
                    "observations": command.observations,
                }
                composed = self._email_composer.compose(
                    command.template_name,
                    command.template_version,
                    context,
                )
                duration_ms = round((time.perf_counter() - started) * 1000)
                rfq = RfqRequest(
                    id=candidate_id,
                    tender_id=tender.id,
                    tender_supplier_id=tender_supplier.id,
                    supplier_id=supplier.id,
                    catalog_snapshot_id=snapshot.id,
                    generated_by_user_id=command.generated_by_user_id,
                    response_deadline=command.response_deadline,
                    template_name=composed.template_name,
                    template_version=composed.template_version,
                    subject=composed.subject,
                    body=composed.body,
                    products=products,
                    generation_key=key,
                    generation_duration_ms=duration_ms,
                    to_recipients=recipients,
                    contact_name=contact_name,
                    observations=command.observations,
                )
                rfq.start_review()
                created = uow.rfqs.create_rfq(rfq)
                stored_attachments = uow.rfqs.replace_attachments(created.id, attachments)
                uow.audit_events.append(
                    rfq_event(
                        created.id,
                        "TemplateRendered",
                        template_name=created.template_name,
                        template_version=created.template_version,
                        content_type=composed.content_type,
                    )
                )
                for attachment in stored_attachments:
                    uow.audit_events.append(
                        rfq_event(
                            created.id,
                            "AttachmentGenerated",
                            attachment_id=str(attachment.id),
                            document_id=str(attachment.document_id),
                            name=attachment.original_file_name,
                            hash=attachment.file_hash,
                            size=attachment.file_size,
                            mime_type=attachment.mime_type,
                        )
                    )
                uow.audit_events.append(
                    rfq_event(
                        created.id,
                        "RfqGenerated",
                        tender_id=str(created.tender_id),
                        tender_supplier_id=str(created.tender_supplier_id),
                        supplier_id=str(created.supplier_id),
                        catalog_snapshot_id=str(created.catalog_snapshot_id),
                        generated_by_user_id=str(created.generated_by_user_id),
                        recipients=list(created.to_recipients),
                        products=len(created.products),
                        attachments=len(stored_attachments),
                        generation_duration_ms=duration_ms,
                    )
                )
                generated.append(_rfq_response(uow, created))
            uow.commit()
        return RfqGenerationResponse(
            tender_id=command.tender_id,
            generated=tuple(generated),
            reused=tuple(reused),
            suppliers_without_email=tuple(suppliers_without_email),
        )


class GetTenderRfqs:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, tender_id: UUID) -> TenderRfqsResponse:
        with self._uow_factory() as uow:
            if uow.tenders.get_by_id(tender_id) is None:
                raise TenderNotFound("Tender was not found.")
            items = uow.rfqs.list_rfqs(tender_id)
            responses = tuple(_rfq_response(uow, item) for item in items)
            messages = [message for item in items for message in uow.rfqs.list_messages(item.id)]
        total = len(items)
        sent = sum(item.status in {RfqStatus.SENT, RfqStatus.DELIVERED} for item in items)
        completed_messages = [message for message in messages if message.duration_ms is not None]
        attachments = [attachment for response in responses for attachment in response.attachments]
        metrics = RfqMetricsResponse(
            total=total,
            pending_review=sum(item.status is RfqStatus.PENDING_REVIEW for item in items),
            approved=sum(item.status is RfqStatus.APPROVED for item in items),
            queued=sum(item.status in {RfqStatus.QUEUED, RfqStatus.SENDING} for item in items),
            sent=sent,
            failed=sum(item.status is RfqStatus.FAILED for item in items),
            cancelled=sum(item.status is RfqStatus.CANCELLED for item in items),
            success_percentage=round(sent / total * 100, 2) if total else 0.0,
            average_attachment_size_bytes=(
                round(sum(item.file_size for item in attachments) / len(attachments), 2)
                if attachments
                else 0.0
            ),
            average_send_duration_ms=(
                round(
                    sum(message.duration_ms or 0 for message in completed_messages)
                    / len(completed_messages),
                    2,
                )
                if completed_messages
                else 0.0
            ),
            retries=sum(max(len(uow_messages) - 1, 0) for uow_messages in (
                [message for message in messages if message.rfq_id == item.id] for item in items
            )),
        )
        return TenderRfqsResponse(tender_id, responses, metrics)


class GetRfq:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, rfq_id: UUID) -> RfqResponse:
        with self._uow_factory() as uow:
            rfq = uow.rfqs.get_rfq(rfq_id)
            if rfq is None:
                raise RfqNotFound("RFQ was not found.")
            return _rfq_response(uow, rfq)


class UpdateRfq:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        attachment_provider: AttachmentProvider,
    ) -> None:
        self._uow_factory = uow_factory
        self._attachment_provider = attachment_provider

    def execute(self, rfq_id: UUID, command: UpdateRfqCommand) -> RfqResponse:
        with self._uow_factory() as uow:
            rfq = uow.rfqs.get_rfq(rfq_id, for_update=True)
            if rfq is None:
                raise RfqNotFound("RFQ was not found.")
            if not uow.users.exists(command.changed_by_user_id):
                raise InvalidRfqState("RFQ editor user does not exist.")
            before = {
                "version": rfq.version,
                "subject": rfq.subject,
                "body": rfq.body,
                "to": rfq.to_recipients,
                "cc": rfq.cc_recipients,
                "bcc": rfq.bcc_recipients,
                "deadline": rfq.response_deadline.isoformat(),
                "observations": rfq.observations,
            }
            rfq.edit(
                subject=command.subject,
                body=command.body,
                to_recipients=command.to_recipients,
                cc_recipients=command.cc_recipients,
                bcc_recipients=command.bcc_recipients,
                response_deadline=command.response_deadline,
                observations=command.observations,
                contact_name=command.contact_name,
            )
            if command.document_ids is not None:
                current_ids = {item.document_id for item in uow.rfqs.list_attachments(rfq.id)}
                requested_ids = set(command.document_ids)
                if current_ids != requested_ids:
                    rfq.record_attachment_edit()
                    attachments = self._attachment_provider.build_metadata(
                        rfq.tender_id, rfq.id, command.document_ids
                    )
                    uow.rfqs.replace_attachments(rfq.id, attachments)
            updated = uow.rfqs.update_rfq(rfq)
            after = {
                "version": updated.version,
                "subject": updated.subject,
                "body": updated.body,
                "to": updated.to_recipients,
                "cc": updated.cc_recipients,
                "bcc": updated.bcc_recipients,
                "deadline": updated.response_deadline.isoformat(),
                "observations": updated.observations,
                "attachment_document_ids": [
                    str(item.document_id) for item in uow.rfqs.list_attachments(updated.id)
                ],
            }
            changed_fields = sorted(key for key in after if before.get(key) != after.get(key))
            uow.audit_events.append(
                rfq_event(
                    updated.id,
                    "RfqEdited",
                    changed_by_user_id=str(command.changed_by_user_id),
                    changed_fields=changed_fields,
                    before=before,
                    after=after,
                )
            )
            uow.commit()
            return _rfq_response(uow, updated)


class ApproveRfq:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, rfq_id: UUID, approved_by_user_id: UUID) -> RfqResponse:
        with self._uow_factory() as uow:
            rfq = uow.rfqs.get_rfq(rfq_id, for_update=True)
            if rfq is None:
                raise RfqNotFound("RFQ was not found.")
            if not uow.users.exists(approved_by_user_id):
                raise InvalidRfqState("RFQ approver user does not exist.")
            attachments = tuple(uow.rfqs.list_attachments(rfq.id))
            rfq.approve(approved_by_user_id, attachments)
            updated = uow.rfqs.update_rfq(rfq)
            uow.audit_events.append(
                rfq_event(
                    updated.id,
                    "RfqApproved",
                    approved_by_user_id=str(approved_by_user_id),
                    approved_at=updated.approved_at.isoformat() if updated.approved_at else None,
                    version=updated.version,
                    idempotency_key=updated.send_idempotency_key,
                    recipients=list(updated.to_recipients),
                    attachments=[item.snapshot() for item in attachments],
                )
            )
            uow.commit()
            return _rfq_response(uow, updated)


class CancelRfq:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, rfq_id: UUID, user_id: UUID, reason: str | None) -> RfqResponse:
        with self._uow_factory() as uow:
            rfq = uow.rfqs.get_rfq(rfq_id, for_update=True)
            if rfq is None:
                raise RfqNotFound("RFQ was not found.")
            if not uow.users.exists(user_id):
                raise InvalidRfqState("RFQ cancellation user does not exist.")
            rfq.cancel(user_id, reason)
            updated = uow.rfqs.update_rfq(rfq)
            uow.audit_events.append(
                rfq_event(
                    updated.id,
                    "RfqCancelled",
                    cancelled_by_user_id=str(user_id),
                    reason=updated.cancellation_reason,
                )
            )
            uow.commit()
            return _rfq_response(uow, updated)


class QueueRfqSend:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        delivery_queue: RfqDeliveryQueue,
    ) -> None:
        self._uow_factory = uow_factory
        self._delivery_queue = delivery_queue

    def execute(self, rfq_id: UUID, requested_by_user_id: UUID) -> RfqResponse:
        with self._uow_factory() as uow:
            rfq = uow.rfqs.get_rfq(rfq_id, for_update=True)
            if rfq is None:
                raise RfqNotFound("RFQ was not found.")
            if not uow.users.exists(requested_by_user_id):
                raise InvalidRfqState("RFQ sender user does not exist.")
            if uow.rfqs.get_sent_message(rfq.id, rfq.version) is not None or rfq.status in {
                RfqStatus.SENT,
                RfqStatus.DELIVERED,
            }:
                raise DuplicateRfqSend("RFQ has already been sent.")
            if rfq.status in {RfqStatus.QUEUED, RfqStatus.SENDING}:
                return _rfq_response(uow, rfq)
            rfq.queue(requested_by_user_id)
            updated = uow.rfqs.update_rfq(rfq)
            uow.audit_events.append(
                rfq_event(
                    updated.id,
                    "RfqQueued",
                    requested_by_user_id=str(requested_by_user_id),
                    version=updated.version,
                    idempotency_key=updated.send_idempotency_key,
                )
            )
            uow.commit()
        try:
            self._delivery_queue.enqueue(updated.id)
        except Exception as exc:
            with self._uow_factory() as uow:
                failed = uow.rfqs.get_rfq(updated.id, for_update=True)
                if failed is not None and failed.status is RfqStatus.QUEUED:
                    failed.mark_failed(f"Unable to enqueue RFQ delivery: {exc}")
                    failed = uow.rfqs.update_rfq(failed)
                    uow.audit_events.append(
                        rfq_event(
                            failed.id,
                            "EmailFailed",
                            stage="queue",
                            error_type=type(exc).__name__,
                            error_message=str(exc)[:4000],
                        )
                    )
                    uow.commit()
            raise EmailDeliveryError("Unable to enqueue RFQ delivery.") from exc
        return self.execute_response(updated.id)

    def execute_response(self, rfq_id: UUID) -> RfqResponse:
        with self._uow_factory() as uow:
            rfq = uow.rfqs.get_rfq(rfq_id)
            if rfq is None:
                raise RfqNotFound("RFQ was not found.")
            return _rfq_response(uow, rfq)


class DeliverRfq:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        attachment_provider: AttachmentProvider,
        email_sender: EmailSender,
    ) -> None:
        self._uow_factory = uow_factory
        self._attachment_provider = attachment_provider
        self._email_sender = email_sender

    def execute(self, rfq_id: UUID) -> UUID:
        with self._uow_factory() as uow:
            rfq = uow.rfqs.get_rfq(rfq_id, for_update=True)
            if rfq is None:
                raise RfqNotFound("RFQ was not found.")
            sent = uow.rfqs.get_sent_message(rfq.id, rfq.version)
            if sent is not None:
                return sent.id
            if rfq.status is RfqStatus.FAILED:
                if rfq.send_requested_by_user_id is None:
                    raise InvalidRfqState("Failed RFQ has no sending user for retry.")
                rfq.queue(rfq.send_requested_by_user_id)
            if rfq.status is RfqStatus.SENDING:
                raise InvalidRfqState(
                    "RFQ delivery is already in progress and will not be duplicated."
                )
            if rfq.status is not RfqStatus.QUEUED:
                raise InvalidRfqState("Only queued RFQs can be delivered.")
            attachments = tuple(uow.rfqs.list_attachments(rfq.id))
            message = EmailMessage(
                rfq_id=rfq.id,
                rfq_version=rfq.version,
                attempt_number=uow.rfqs.next_attempt_number(rfq.id),
                idempotency_key=rfq.send_idempotency_key or "",
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
            created_message = uow.rfqs.create_message(message)
            rfq.start_sending()
            uow.rfqs.update_rfq(rfq)
            uow.rfqs.add_log(
                OutboundMessageLog(
                    rfq_id=rfq.id,
                    email_message_id=created_message.id,
                    event_type="EmailSendingStarted",
                    result=OutboundLogResult.RECORDED,
                    provider_name=self._email_sender.provider_name,
                    details={
                        "attempt": created_message.attempt_number,
                        "recipients": list(created_message.to_recipients),
                        "subject": created_message.subject,
                        "attachments": list(created_message.attachment_snapshot),
                    },
                )
            )
            uow.audit_events.append(
                rfq_event(
                    rfq.id,
                    "EmailSendingStarted",
                    message_id=str(created_message.id),
                    attempt=created_message.attempt_number,
                    provider=self._email_sender.provider_name,
                    recipients=list(created_message.to_recipients),
                    subject=created_message.subject,
                    attachments=list(created_message.attachment_snapshot),
                )
            )
            uow.audit_events.append(
                rfq_event(
                    rfq.id,
                    "OutboundMessageRecorded",
                    message_id=str(created_message.id),
                    result="recorded",
                )
            )
            uow.commit()

        started = time.perf_counter()
        try:
            content = self._attachment_provider.load(attachments)
            result = self._email_sender.send(created_message, content)
        except Exception as exc:
            duration_ms = round((time.perf_counter() - started) * 1000)
            with self._uow_factory() as uow:
                failed_rfq = uow.rfqs.get_rfq(rfq_id, for_update=True)
                failed_message = uow.rfqs.get_message(created_message.id, for_update=True)
                if failed_rfq is not None and failed_message is not None:
                    failed_message.fail(exc, duration_ms)
                    uow.rfqs.update_message(failed_message)
                    failed_rfq.mark_failed(str(exc))
                    uow.rfqs.update_rfq(failed_rfq)
                    details = {
                        "attempt": failed_message.attempt_number,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc)[:4000],
                        "duration_ms": duration_ms,
                    }
                    uow.rfqs.add_log(
                        OutboundMessageLog(
                            rfq_id=failed_rfq.id,
                            email_message_id=failed_message.id,
                            event_type="EmailFailed",
                            result=OutboundLogResult.FAILURE,
                            provider_name=self._email_sender.provider_name,
                            details=details,
                        )
                    )
                    uow.audit_events.append(
                        rfq_event(
                            failed_rfq.id,
                            "EmailFailed",
                            message_id=str(failed_message.id),
                            provider=self._email_sender.provider_name,
                            **details,
                        )
                    )
                    uow.audit_events.append(
                        rfq_event(
                            failed_rfq.id,
                            "OutboundMessageRecorded",
                            message_id=str(failed_message.id),
                            result="failure",
                        )
                    )
                    uow.commit()
            if isinstance(exc, EmailDeliveryError):
                raise
            raise EmailDeliveryError("RFQ email delivery failed.") from exc

        with self._uow_factory() as uow:
            sent_rfq = uow.rfqs.get_rfq(rfq_id, for_update=True)
            sent_message = uow.rfqs.get_message(created_message.id, for_update=True)
            if sent_rfq is None or sent_message is None:
                raise RfqNotFound("RFQ delivery state was not found.")
            sent_message.succeed(result.external_message_id, result.duration_ms)
            uow.rfqs.update_message(sent_message)
            sent_rfq.mark_sent()
            uow.rfqs.update_rfq(sent_rfq)
            details = {
                "attempt": sent_message.attempt_number,
                "external_message_id": result.external_message_id,
                "duration_ms": result.duration_ms,
                "recipients": list(sent_message.to_recipients),
                "attachments": list(sent_message.attachment_snapshot),
            }
            uow.rfqs.add_log(
                OutboundMessageLog(
                    rfq_id=sent_rfq.id,
                    email_message_id=sent_message.id,
                    event_type="EmailSent",
                    result=OutboundLogResult.SUCCESS,
                    provider_name=result.provider_name,
                    details=details,
                )
            )
            uow.audit_events.append(
                rfq_event(
                    sent_rfq.id,
                    "EmailSent",
                    message_id=str(sent_message.id),
                    provider=result.provider_name,
                    sent_by_user_id=str(sent_rfq.send_requested_by_user_id),
                    subject=sent_message.subject,
                    **details,
                )
            )
            uow.audit_events.append(
                rfq_event(
                    sent_rfq.id,
                    "OutboundMessageRecorded",
                    message_id=str(sent_message.id),
                    result="success",
                )
            )
            uow.commit()
            logger.info(
                "rfq_email_sent",
                extra={
                    "rfq_id": str(sent_rfq.id),
                    "message_id": str(sent_message.id),
                    "attempt": sent_message.attempt_number,
                    "provider": result.provider_name,
                    "duration_ms": result.duration_ms,
                    "attachment_count": len(attachments),
                },
            )
            return sent_message.id


class GetRfqMessages:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, rfq_id: UUID) -> RfqMessagesResponse:
        with self._uow_factory() as uow:
            if uow.rfqs.get_rfq(rfq_id) is None:
                raise RfqNotFound("RFQ was not found.")
            messages = tuple(_message_response(item) for item in uow.rfqs.list_messages(rfq_id))
            logs = tuple(
                OutboundLogResponse(
                    id=item.id,
                    event_type=item.event_type,
                    result=item.result,
                    provider_name=item.provider_name,
                    details=item.details,
                    occurred_at=item.occurred_at,
                )
                for item in uow.rfqs.list_logs(rfq_id)
            )
        return RfqMessagesResponse(rfq_id, messages, logs)
