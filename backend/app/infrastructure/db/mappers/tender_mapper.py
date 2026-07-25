from app.domain.shared.value_objects import FileHash
from app.domain.tenders.entities import Tender, TenderDocument
from app.domain.tenders.value_objects import DocumentStatus, TenderStatus
from app.infrastructure.db.models.tender import TenderDocumentModel, TenderModel


def tender_document_to_model(document: TenderDocument) -> TenderDocumentModel:
    return TenderDocumentModel(
        id=document.id,
        tender_id=document.tender_id,
        file_name=document.file_name,
        file_path=document.file_path,
        mime_type=document.mime_type,
        file_size=document.file_size,
        file_hash=document.file_hash.value,
        document_type=document.document_type,
        processing_status=document.processing_status.value,
        requires_ocr=document.requires_ocr,
        uploaded_by_user_id=document.uploaded_by_user_id,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def tender_to_model(tender: Tender) -> TenderModel:
    model = TenderModel(
        id=tender.id,
        title=tender.title,
        description=tender.description,
        status=tender.status.value,
        deadline=tender.deadline,
        created_by_user_id=tender.created_by_user_id,
        created_at=tender.created_at,
        updated_at=tender.updated_at,
        deleted_at=tender.deleted_at,
    )
    model.documents = [tender_document_to_model(document) for document in tender.documents]
    return model


def tender_document_to_domain(model: TenderDocumentModel) -> TenderDocument:
    return TenderDocument(
        id=model.id,
        tender_id=model.tender_id,
        file_name=model.file_name,
        file_path=model.file_path,
        mime_type=model.mime_type,
        file_size=model.file_size,
        file_hash=FileHash(model.file_hash),
        document_type=model.document_type,
        processing_status=DocumentStatus(model.processing_status),
        requires_ocr=model.requires_ocr,
        uploaded_by_user_id=model.uploaded_by_user_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def tender_to_domain(model: TenderModel) -> Tender:
    return Tender(
        id=model.id,
        title=model.title,
        description=model.description,
        status=TenderStatus(model.status),
        deadline=model.deadline,
        created_by_user_id=model.created_by_user_id,
        documents=[tender_document_to_domain(document) for document in model.documents],
        created_at=model.created_at,
        updated_at=model.updated_at,
        deleted_at=model.deleted_at,
    )


def update_tender_model(model: TenderModel, tender: Tender) -> None:
    model.title = tender.title
    model.description = tender.description
    model.status = tender.status.value
    model.deadline = tender.deadline
    model.updated_at = tender.updated_at
    model.deleted_at = tender.deleted_at

    documents_by_id = {document.id: document for document in model.documents}
    incoming_ids = {document.id for document in tender.documents}

    for document in list(model.documents):
        if document.id not in incoming_ids:
            model.documents.remove(document)

    for document in tender.documents:
        existing = documents_by_id.get(document.id)
        if existing is None:
            model.documents.append(tender_document_to_model(document))
            continue

        existing.file_name = document.file_name
        existing.file_path = document.file_path
        existing.mime_type = document.mime_type
        existing.file_size = document.file_size
        existing.file_hash = document.file_hash.value
        existing.document_type = document.document_type
        existing.processing_status = document.processing_status.value
        existing.requires_ocr = document.requires_ocr
        existing.uploaded_by_user_id = document.uploaded_by_user_id
        existing.updated_at = document.updated_at

