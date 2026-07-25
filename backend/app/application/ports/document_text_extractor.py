from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExtractedPage:
    page_number: int
    text: str
    width: float
    height: float
    duration_ms: int

    @property
    def character_count(self) -> int:
        return len(self.text.strip())

    @property
    def is_empty(self) -> bool:
        return self.character_count < 5


@dataclass(frozen=True, slots=True)
class TextExtractionResult:
    extractor_name: str
    extractor_version: str
    pages: tuple[ExtractedPage, ...]
    duration_ms: int

    @property
    def characters_extracted(self) -> int:
        return sum(page.character_count for page in self.pages)

    @property
    def empty_page_percentage(self) -> float:
        if not self.pages:
            return 100.0
        empty = sum(page.is_empty for page in self.pages)
        return (empty / len(self.pages)) * 100.0


class DocumentTextExtractor(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def version(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def extract(self, content: bytes) -> TextExtractionResult:
        raise NotImplementedError
