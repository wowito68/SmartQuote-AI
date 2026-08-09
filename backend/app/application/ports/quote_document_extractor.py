from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.domain.quotes.value_objects import QuoteDocumentType


@dataclass(frozen=True, slots=True)
class ExtractedQuoteSection:
    sequence: int
    locator_type: str
    locator: str
    text: str
    extraction_method: str
    page_number: int | None = None


@dataclass(frozen=True, slots=True)
class QuoteDocumentExtractionResult:
    document_type: QuoteDocumentType
    extractor_name: str
    extractor_version: str
    sections: tuple[ExtractedQuoteSection, ...]
    duration_ms: int


class QuoteDocumentExtractor(ABC):
    @abstractmethod
    def extract(
        self,
        document_type: QuoteDocumentType,
        content: bytes,
    ) -> QuoteDocumentExtractionResult:
        raise NotImplementedError

    @property
    @abstractmethod
    def version(self) -> str:
        raise NotImplementedError
