from app.domain.documents.entities import TenderDocument
from app.domain.documents.value_objects import DocumentStatus, FileHash
from app.infrastructure.db.models.tender import TenderDocumentModel


def tender_document_to_model(document: TenderDocument) -> TenderDocumentModel:
    return TenderDocumentModel(
        id=document.id,
        tender_id=document.tender_id,
        file_name=document.original_file_name,
        file_path=document.storage_key,
        mime_type=document.mime_type,
        file_size=document.file_size,
        file_hash=document.file_hash.value,
        document_type="tender_pdf",
        processing_status=document.status.value,
        requires_ocr=document.requires_ocr,
        uploaded_by_user_id=document.uploaded_by_user_id,
        created_at=document.created_at,
        updated_at=document.updated_at,
        deleted_at=document.deleted_at,
        queued_at=document.queued_at,
        processing_started_at=document.processing_started_at,
        processed_at=document.processed_at,
        last_processing_error=document.last_processing_error,
    )


def tender_document_to_domain(model: TenderDocumentModel) -> TenderDocument:
    return TenderDocument(
        id=model.id,
        tender_id=model.tender_id,
        original_file_name=model.file_name,
        storage_key=model.file_path,
        mime_type=model.mime_type,
        file_size=model.file_size,
        file_hash=FileHash(model.file_hash),
        status=DocumentStatus(model.processing_status),
        requires_ocr=model.requires_ocr,
        uploaded_by_user_id=model.uploaded_by_user_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        deleted_at=model.deleted_at,
        queued_at=model.queued_at,
        processing_started_at=model.processing_started_at,
        processed_at=model.processed_at,
        last_processing_error=model.last_processing_error,
    )


def update_tender_document_model(
    model: TenderDocumentModel,
    document: TenderDocument,
) -> None:
    model.file_name = document.original_file_name
    model.file_path = document.storage_key
    model.mime_type = document.mime_type
    model.file_size = document.file_size
    model.file_hash = document.file_hash.value
    model.processing_status = document.status.value
    model.requires_ocr = document.requires_ocr
    model.uploaded_by_user_id = document.uploaded_by_user_id
    model.updated_at = document.updated_at
    model.deleted_at = document.deleted_at
    model.queued_at = document.queued_at
    model.processing_started_at = document.processing_started_at
    model.processed_at = document.processed_at
    model.last_processing_error = document.last_processing_error
