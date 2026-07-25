from enum import StrEnum

from app.domain.documents.value_objects import DocumentStatus


class TenderStatus(StrEnum):
    DRAFT = "draft"
    DOCUMENTS_PENDING = "documents_pending"
    DOCUMENTS_PROCESSING = "documents_processing"
    CATALOG_REVIEW = "catalog_review"
    CANCELLED = "cancelled"
    CLOSED = "closed"


__all__ = ["DocumentStatus", "TenderStatus"]
