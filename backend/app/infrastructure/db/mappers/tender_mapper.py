from app.domain.tenders.entities import Tender
from app.domain.tenders.value_objects import TenderStatus
from app.infrastructure.db.mappers.document_mapper import (
    tender_document_to_domain,
    tender_document_to_model,
)
from app.infrastructure.db.models.tender import TenderModel


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
