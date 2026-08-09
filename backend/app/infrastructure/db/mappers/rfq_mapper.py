from app.domain.rfqs.entities import (
    EmailAttachment,
    EmailMessage,
    OutboundMessageLog,
    RfqRequest,
    RfqTaskRecord,
    RfqVersionSnapshot,
)
from app.domain.rfqs.value_objects import (
    EmailMessageStatus,
    OutboundLogResult,
    RfqStatus,
    TaskRecordStatus,
)
from app.infrastructure.db.models.rfq import (
    EmailAttachmentModel,
    EmailMessageModel,
    OutboundMessageLogModel,
    RfqRequestModel,
    RfqTaskRecordModel,
    RfqVersionModel,
)


def rfq_to_model(rfq: RfqRequest) -> RfqRequestModel:
    return RfqRequestModel(
        id=rfq.id,
        tender_id=rfq.tender_id,
        tender_supplier_id=rfq.tender_supplier_id,
        supplier_id=rfq.supplier_id,
        contact_id=rfq.contact_id,
        catalog_snapshot_id=rfq.catalog_snapshot_id,
        generated_by_user_id=rfq.generated_by_user_id,
        response_deadline=rfq.response_deadline,
        template_name=rfq.template_name,
        template_version=rfq.template_version,
        subject=rfq.subject,
        body=rfq.body,
        products=list(rfq.products),
        generation_key=rfq.generation_key,
        generation_duration_ms=rfq.generation_duration_ms,
        to_recipients=list(rfq.to_recipients),
        cc_recipients=list(rfq.cc_recipients),
        bcc_recipients=list(rfq.bcc_recipients),
        contact_name=rfq.contact_name,
        observations=rfq.observations,
        status=rfq.status.value,
        version=rfq.version,
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
        created_at=rfq.created_at,
        updated_at=rfq.updated_at,
    )


def rfq_to_domain(model: RfqRequestModel) -> RfqRequest:
    return RfqRequest(
        id=model.id,
        tender_id=model.tender_id,
        tender_supplier_id=model.tender_supplier_id,
        supplier_id=model.supplier_id,
        contact_id=model.contact_id,
        catalog_snapshot_id=model.catalog_snapshot_id,
        generated_by_user_id=model.generated_by_user_id,
        response_deadline=model.response_deadline,
        template_name=model.template_name,
        template_version=model.template_version,
        subject=model.subject,
        body=model.body,
        products=tuple(model.products or []),
        generation_key=model.generation_key,
        generation_duration_ms=model.generation_duration_ms,
        to_recipients=tuple(model.to_recipients or []),
        cc_recipients=tuple(model.cc_recipients or []),
        bcc_recipients=tuple(model.bcc_recipients or []),
        contact_name=model.contact_name,
        observations=model.observations,
        status=RfqStatus(model.status),
        version=model.version,
        approved_by_user_id=model.approved_by_user_id,
        approved_at=model.approved_at,
        send_requested_by_user_id=model.send_requested_by_user_id,
        queued_at=model.queued_at,
        sending_started_at=model.sending_started_at,
        sent_at=model.sent_at,
        delivered_at=model.delivered_at,
        cancelled_by_user_id=model.cancelled_by_user_id,
        cancelled_at=model.cancelled_at,
        cancellation_reason=model.cancellation_reason,
        last_error=model.last_error,
        send_idempotency_key=model.send_idempotency_key,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def update_rfq_model(model: RfqRequestModel, rfq: RfqRequest) -> None:
    model.contact_id = rfq.contact_id
    model.response_deadline = rfq.response_deadline
    model.subject = rfq.subject
    model.body = rfq.body
    model.products = list(rfq.products)
    model.to_recipients = list(rfq.to_recipients)
    model.cc_recipients = list(rfq.cc_recipients)
    model.bcc_recipients = list(rfq.bcc_recipients)
    model.contact_name = rfq.contact_name
    model.observations = rfq.observations
    model.status = rfq.status.value
    model.version = rfq.version
    model.approved_by_user_id = rfq.approved_by_user_id
    model.approved_at = rfq.approved_at
    model.send_requested_by_user_id = rfq.send_requested_by_user_id
    model.queued_at = rfq.queued_at
    model.sending_started_at = rfq.sending_started_at
    model.sent_at = rfq.sent_at
    model.delivered_at = rfq.delivered_at
    model.cancelled_by_user_id = rfq.cancelled_by_user_id
    model.cancelled_at = rfq.cancelled_at
    model.cancellation_reason = rfq.cancellation_reason
    model.last_error = rfq.last_error
    model.send_idempotency_key = rfq.send_idempotency_key
    model.updated_at = rfq.updated_at


def version_to_model(item: RfqVersionSnapshot) -> RfqVersionModel:
    return RfqVersionModel(
        id=item.id,
        rfq_id=item.rfq_id,
        version=item.version,
        changed_by_user_id=item.changed_by_user_id,
        status=item.status.value,
        contact_id=item.contact_id,
        subject=item.subject,
        body=item.body,
        to_recipients=list(item.to_recipients),
        cc_recipients=list(item.cc_recipients),
        bcc_recipients=list(item.bcc_recipients),
        products=list(item.products),
        attachment_snapshot=list(item.attachment_snapshot),
        change_reason=item.change_reason,
        created_at=item.created_at,
    )


def version_to_domain(model: RfqVersionModel) -> RfqVersionSnapshot:
    return RfqVersionSnapshot(
        id=model.id,
        rfq_id=model.rfq_id,
        version=model.version,
        changed_by_user_id=model.changed_by_user_id,
        status=RfqStatus(model.status),
        contact_id=model.contact_id,
        subject=model.subject,
        body=model.body,
        to_recipients=tuple(model.to_recipients or []),
        cc_recipients=tuple(model.cc_recipients or []),
        bcc_recipients=tuple(model.bcc_recipients or []),
        products=tuple(model.products or []),
        attachment_snapshot=tuple(model.attachment_snapshot or []),
        change_reason=model.change_reason,
        created_at=model.created_at,
    )


def attachment_to_model(item: EmailAttachment) -> EmailAttachmentModel:
    return EmailAttachmentModel(
        id=item.id,
        rfq_id=item.rfq_id,
        document_id=item.document_id,
        original_file_name=item.original_file_name,
        file_hash=item.file_hash,
        file_size=item.file_size,
        mime_type=item.mime_type,
        created_at=item.created_at,
    )


def attachment_to_domain(model: EmailAttachmentModel) -> EmailAttachment:
    return EmailAttachment(
        id=model.id,
        rfq_id=model.rfq_id,
        document_id=model.document_id,
        original_file_name=model.original_file_name,
        file_hash=model.file_hash,
        file_size=model.file_size,
        mime_type=model.mime_type,
        created_at=model.created_at,
    )


def message_to_model(item: EmailMessage) -> EmailMessageModel:
    return EmailMessageModel(
        id=item.id,
        rfq_id=item.rfq_id,
        rfq_version=item.rfq_version,
        attempt_number=item.attempt_number,
        idempotency_key=item.idempotency_key,
        provider_name=item.provider_name,
        from_address=item.from_address,
        to_recipients=list(item.to_recipients),
        cc_recipients=list(item.cc_recipients),
        bcc_recipients=list(item.bcc_recipients),
        subject=item.subject,
        body=item.body,
        attachment_snapshot=list(item.attachment_snapshot),
        status=item.status.value,
        external_message_id=item.external_message_id,
        error_type=item.error_type,
        error_message=item.error_message,
        started_at=item.started_at,
        sent_at=item.sent_at,
        failed_at=item.failed_at,
        duration_ms=item.duration_ms,
        created_at=item.created_at,
    )


def message_to_domain(model: EmailMessageModel) -> EmailMessage:
    return EmailMessage(
        id=model.id,
        rfq_id=model.rfq_id,
        rfq_version=model.rfq_version,
        attempt_number=model.attempt_number,
        idempotency_key=model.idempotency_key,
        provider_name=model.provider_name,
        from_address=model.from_address,
        to_recipients=tuple(model.to_recipients or []),
        cc_recipients=tuple(model.cc_recipients or []),
        bcc_recipients=tuple(model.bcc_recipients or []),
        subject=model.subject,
        body=model.body,
        attachment_snapshot=tuple(model.attachment_snapshot or []),
        status=EmailMessageStatus(model.status),
        external_message_id=model.external_message_id,
        error_type=model.error_type,
        error_message=model.error_message,
        started_at=model.started_at,
        sent_at=model.sent_at,
        failed_at=model.failed_at,
        duration_ms=model.duration_ms,
        created_at=model.created_at,
    )


def update_message_model(model: EmailMessageModel, item: EmailMessage) -> None:
    model.status = item.status.value
    model.external_message_id = item.external_message_id
    model.error_type = item.error_type
    model.error_message = item.error_message
    model.started_at = item.started_at
    model.sent_at = item.sent_at
    model.failed_at = item.failed_at
    model.duration_ms = item.duration_ms


def task_to_model(item: RfqTaskRecord) -> RfqTaskRecordModel:
    return RfqTaskRecordModel(
        id=item.id,
        rfq_id=item.rfq_id,
        correlation_id=item.correlation_id,
        task_name=item.task_name,
        status=item.status.value,
        attempt_count=item.attempt_count,
        last_error=item.last_error,
        queued_at=item.queued_at,
        started_at=item.started_at,
        completed_at=item.completed_at,
        updated_at=item.updated_at,
    )


def task_to_domain(model: RfqTaskRecordModel) -> RfqTaskRecord:
    return RfqTaskRecord(
        id=model.id,
        rfq_id=model.rfq_id,
        correlation_id=model.correlation_id,
        task_name=model.task_name,
        status=TaskRecordStatus(model.status),
        attempt_count=model.attempt_count,
        last_error=model.last_error,
        queued_at=model.queued_at,
        started_at=model.started_at,
        completed_at=model.completed_at,
        updated_at=model.updated_at,
    )


def update_task_model(model: RfqTaskRecordModel, item: RfqTaskRecord) -> None:
    model.status = item.status.value
    model.attempt_count = item.attempt_count
    model.last_error = item.last_error
    model.started_at = item.started_at
    model.completed_at = item.completed_at
    model.updated_at = item.updated_at


def log_to_model(item: OutboundMessageLog) -> OutboundMessageLogModel:
    return OutboundMessageLogModel(
        id=item.id,
        rfq_id=item.rfq_id,
        email_message_id=item.email_message_id,
        event_type=item.event_type,
        result=item.result.value,
        provider_name=item.provider_name,
        details=item.details,
        occurred_at=item.occurred_at,
    )


def log_to_domain(model: OutboundMessageLogModel) -> OutboundMessageLog:
    return OutboundMessageLog(
        id=model.id,
        rfq_id=model.rfq_id,
        email_message_id=model.email_message_id,
        event_type=model.event_type,
        result=OutboundLogResult(model.result),
        provider_name=model.provider_name,
        details=dict(model.details or {}),
        occurred_at=model.occurred_at,
    )
