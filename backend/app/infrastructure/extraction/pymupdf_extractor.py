from time import perf_counter

import pymupdf

from app.application.ports.document_text_extractor import (
    DocumentTextExtractor,
    ExtractedPage,
    TextExtractionResult,
)


class PyMuPDFExtractor(DocumentTextExtractor):
    @property
    def name(self) -> str:
        return "pymupdf"

    @property
    def version(self) -> str:
        return pymupdf.__version__

    def extract(self, content: bytes) -> TextExtractionResult:
        started = perf_counter()
        pages: list[ExtractedPage] = []
        with pymupdf.open(stream=content, filetype="pdf") as document:
            for index, page in enumerate(document, start=1):
                page_started = perf_counter()
                text = page.get_text("text", sort=True) or ""
                pages.append(
                    ExtractedPage(
                        page_number=index,
                        text=text,
                        width=float(page.rect.width),
                        height=float(page.rect.height),
                        duration_ms=max(int((perf_counter() - page_started) * 1000), 0),
                    )
                )
        return TextExtractionResult(
            extractor_name=self.name,
            extractor_version=self.version,
            pages=tuple(pages),
            duration_ms=max(int((perf_counter() - started) * 1000), 0),
        )
