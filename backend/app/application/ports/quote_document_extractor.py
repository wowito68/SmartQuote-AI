from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class QuoteDocumentSegment:
    ordinal: int
    location_type: str
    location_label: str
    text: str
    tables: tuple[tuple[tuple[str, ...], ...], ...] = ()
    method: str = "text"


@dataclass(frozen=True, slots=True)
class QuoteDocumentExtractionResult:
    extractor_name: str
    extractor_version: str
    segments: tuple[QuoteDocumentSegment, ...]
    duration_ms: int
    metadata: dict[str, Any]


class QuoteDocumentExtractor(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def version(self) -> str: ...

    @abstractmethod
    def supports(self, mime_type: str) -> bool: ...

    @abstractmethod
    def extract(self, content: bytes, mime_type: str) -> QuoteDocumentExtractionResult: ...
