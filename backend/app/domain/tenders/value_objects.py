from enum import StrEnum

from app.domain.documents.value_objects import DocumentStatus


class TenderStatus(StrEnum):
    DRAFT = "draft"
    DOCUMENTS_PENDING = "documents_pending"
    DOCUMENTS_PROCESSING = "documents_processing"
    CATALOG_REVIEW = "catalog_review"
    SUPPLIER_REVIEW = "supplier_review"
    RFQ_READY = "rfq_ready"
    WAITING_QUOTES = "waiting_quotes"
    QUOTE_ANALYSIS = "quote_analysis"
    COMPARISON_READY = "comparison_ready"
    AWARDED = "awarded"
    CANCELLED = "cancelled"
    CLOSED = "closed"


__all__ = ["DocumentStatus", "TenderStatus"]
