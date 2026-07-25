from enum import StrEnum

from app.domain.shared.value_objects import FileHash


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    DELETED = "deleted"
    REJECTED = "rejected"


__all__ = ["DocumentStatus", "FileHash"]
