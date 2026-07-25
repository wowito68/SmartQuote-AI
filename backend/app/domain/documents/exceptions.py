from app.domain.shared.exceptions import DomainError


class DocumentError(DomainError):
    """Base exception for document business-rule violations."""


class DocumentNotFound(DocumentError):
    """Raised when a document cannot be found."""


class DocumentAlreadyDeleted(DocumentError):
    """Raised when an operation targets a deleted document."""


class DuplicateDocument(DocumentError):
    """Raised when the same file hash already exists for a tender."""


class InvalidDocumentFile(DocumentError):
    """Raised when a file does not satisfy the accepted PDF contract."""


class DocumentTooLarge(DocumentError):
    """Raised when a file exceeds the configured maximum size."""


class TooManyDocuments(DocumentError):
    """Raised when one request exceeds the configured file-count limit."""


class DocumentUploaderNotFound(DocumentError):
    """Raised when the uploader does not exist."""


class DocumentStorageFailure(DocumentError):
    """Raised when private file storage cannot complete an operation."""
