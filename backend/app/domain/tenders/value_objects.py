from enum import StrEnum


class TenderStatus(StrEnum):
    DRAFT = "draft"
    DOCUMENTS_PENDING = "documents_pending"
    DOCUMENTS_PROCESSING = "documents_processing"
    CATALOG_REVIEW = "catalog_review"
    CANCELLED = "cancelled"
    CLOSED = "closed"


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    VALIDATING = "validating"
    VALID = "valid"
    STORED = "stored"
    EXTRACTING_TEXT = "extracting_text"
    TEXT_EXTRACTED = "text_extracted"
    NEEDS_OCR = "needs_ocr"
    PROCESSED = "processed"
    REJECTED = "rejected"
    FAILED = "failed"

