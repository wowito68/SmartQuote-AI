from pathlib import Path

import pytest

from app.application.dtos.document import UploadDocumentFile
from app.application.ports.document_text_extractor import (
    DocumentTextExtractor,
    ExtractedPage,
    TextExtractionResult,
)
from app.application.services.quote_document_validation import QuoteDocumentValidator
from app.domain.documents.exceptions import InvalidDocumentFile
from app.domain.quotes.value_objects import QuoteDocumentType
from app.infrastructure.extraction.quote_document_extractor import (
    MultiFormatQuoteDocumentExtractor,
)
from tests.fixtures.quote_files import minimal_docx_bytes, minimal_xlsx_bytes

FIXTURES = Path(__file__).parents[2] / "fixtures"


class PdfExtractor(DocumentTextExtractor):
    @property
    def name(self) -> str:
        return "test-pdf"

    @property
    def version(self) -> str:
        return "1.0"

    def extract(self, content: bytes) -> TextExtractionResult:
        assert content.startswith(b"%PDF-")
        return TextExtractionResult(
            extractor_name=self.name,
            extractor_version=self.version,
            pages=(
                ExtractedPage(
                    page_number=1,
                    text="Cotizacion sensor 1250 MXN",
                    width=100,
                    height=100,
                    duration_ms=1,
                ),
            ),
            duration_ms=1,
        )


def test_validator_accepts_pdf_xlsx_docx_and_rejects_macro_extensions() -> None:
    validator = QuoteDocumentValidator(5_000_000)
    pdf = (FIXTURES / "sample_text.pdf").read_bytes()

    assert validator.validate(
        UploadDocumentFile("quote.pdf", "application/pdf", pdf)
    ).document_type is QuoteDocumentType.PDF
    assert validator.validate(
        UploadDocumentFile(
            "quote.xlsx",
            QuoteDocumentValidator.XLSX_MIME,
            minimal_xlsx_bytes(),
        )
    ).document_type is QuoteDocumentType.XLSX
    assert validator.validate(
        UploadDocumentFile(
            "quote.docx",
            QuoteDocumentValidator.DOCX_MIME,
            minimal_docx_bytes(),
        )
    ).document_type is QuoteDocumentType.DOCX

    with pytest.raises(InvalidDocumentFile):
        validator.validate(
            UploadDocumentFile(
                "quote.xlsm",
                "application/vnd.ms-excel.sheet.macroEnabled.12",
                minimal_xlsx_bytes(),
            )
        )


def test_ooxml_extractors_preserve_locators_and_do_not_evaluate_formulas() -> None:
    extractor = MultiFormatQuoteDocumentExtractor(PdfExtractor())

    xlsx = extractor.extract(
        QuoteDocumentType.XLSX,
        minimal_xlsx_bytes(formula="SUM(1,1)"),
    )
    assert xlsx.sections[0].locator == "sheet:Cotizacion:row:1"
    assert "1250.00" in xlsx.sections[0].text
    assert "SUM" not in xlsx.sections[0].text

    docx = extractor.extract(QuoteDocumentType.DOCX, minimal_docx_bytes())
    assert any(section.locator == "paragraph:1" for section in docx.sections)
    assert any(section.locator == "table:1:row:1" for section in docx.sections)
