from pathlib import Path

from app.application.ports.document_text_extractor import (
    DocumentTextExtractor,
    ExtractedPage,
    TextExtractionResult,
)
from app.application.services.extraction_strategy import (
    ExtractionPolicy,
    FallbackDocumentTextExtractor,
)
from app.infrastructure.extraction.pdfplumber_extractor import PdfPlumberExtractor
from app.infrastructure.extraction.pymupdf_extractor import PyMuPDFExtractor

FIXTURES = Path(__file__).parents[2] / "fixtures"


class StubExtractor(DocumentTextExtractor):
    def __init__(self, name: str, text: str) -> None:
        self._name = name
        self._text = text
        self.calls = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def version(self) -> str:
        return "1.0"

    def extract(self, content: bytes) -> TextExtractionResult:
        self.calls += 1
        return TextExtractionResult(
            extractor_name=self.name,
            extractor_version=self.version,
            pages=(ExtractedPage(1, self._text, 612, 792, 1),),
            duration_ms=1,
        )


def test_pymupdf_and_pdfplumber_extract_real_pdf() -> None:
    content = (FIXTURES / "sample_text.pdf").read_bytes()
    pymupdf_result = PyMuPDFExtractor().extract(content)
    plumber_result = PdfPlumberExtractor().extract(content)
    assert len(pymupdf_result.pages) == 2
    assert "SmartQuote" in pymupdf_result.pages[0].text
    assert "SmartQuote" in plumber_result.pages[0].text


def test_fallback_runs_when_primary_is_insufficient() -> None:
    primary = StubExtractor("primary", "")
    fallback = StubExtractor("fallback", "useful text " * 30)
    strategy = FallbackDocumentTextExtractor(
        primary,
        fallback,
        ExtractionPolicy(minimum_characters=100),
    )
    result = strategy.extract(b"pdf")
    assert primary.calls == 1
    assert fallback.calls == 1
    assert result.extractor_name == "fallback"


def test_processing_key_is_stable_and_configuration_sensitive() -> None:
    primary = StubExtractor("primary", "text")
    fallback = StubExtractor("fallback", "text")
    first = FallbackDocumentTextExtractor(primary, fallback, ExtractionPolicy(100))
    second = FallbackDocumentTextExtractor(primary, fallback, ExtractionPolicy(200))
    assert first.processing_key("a" * 64) == first.processing_key("a" * 64)
    assert first.processing_key("a" * 64) != second.processing_key("a" * 64)
