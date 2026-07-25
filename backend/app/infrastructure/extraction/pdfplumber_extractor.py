from importlib.metadata import version
from io import BytesIO
from time import perf_counter

import pdfplumber

from app.application.ports.document_text_extractor import (
    DocumentTextExtractor,
    ExtractedPage,
    TextExtractionResult,
)


class PdfPlumberExtractor(DocumentTextExtractor):
    @property
    def name(self) -> str:
        return "pdfplumber"

    @property
    def version(self) -> str:
        return version("pdfplumber")

    def extract(self, content: bytes) -> TextExtractionResult:
        started = perf_counter()
        pages: list[ExtractedPage] = []
        with pdfplumber.open(BytesIO(content)) as document:
            for index, page in enumerate(document.pages, start=1):
                page_started = perf_counter()
                text = page.extract_text() or ""
                pages.append(
                    ExtractedPage(
                        page_number=index,
                        text=text,
                        width=float(page.width),
                        height=float(page.height),
                        duration_ms=max(int((perf_counter() - page_started) * 1000), 0),
                    )
                )
        return TextExtractionResult(
            extractor_name=self.name,
            extractor_version=self.version,
            pages=tuple(pages),
            duration_ms=max(int((perf_counter() - started) * 1000), 0),
        )
