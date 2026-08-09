import time
from io import BytesIO
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from app.application.ports.quote_document_extractor import (
    QuoteDocumentExtractionResult,
    QuoteDocumentExtractor,
    QuoteDocumentSegment,
)
from app.application.services.quote_document_validation import DOCX_MIME, PDF_MIME, XLSX_MIME
from app.application.ports.document_text_extractor import DocumentTextExtractor
from app.domain.quotes.exceptions import QuoteExtractionFailure

_NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_NS_DOC = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_REL_NS = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}


class PdfQuoteDocumentExtractor(QuoteDocumentExtractor):
    def __init__(self, extractor: DocumentTextExtractor) -> None:
        self._extractor = extractor

    @property
    def name(self) -> str:
        return f"quote-pdf:{self._extractor.name}"

    @property
    def version(self) -> str:
        return self._extractor.version

    def supports(self, mime_type: str) -> bool:
        return mime_type == PDF_MIME

    def extract(self, content: bytes, mime_type: str) -> QuoteDocumentExtractionResult:
        if not self.supports(mime_type):
            raise QuoteExtractionFailure("PDF quote extractor received an unsupported MIME type.")
        result = self._extractor.extract(content)
        segments = tuple(
            QuoteDocumentSegment(
                ordinal=page.page_number,
                location_type="page",
                location_label=str(page.page_number),
                text=page.text,
                method=result.extractor_name,
            )
            for page in result.pages
        )
        return QuoteDocumentExtractionResult(
            self.name, self.version, segments, result.duration_ms, {"pages": len(segments)}
        )


class XlsxQuoteDocumentExtractor(QuoteDocumentExtractor):
    @property
    def name(self) -> str:
        return "xlsx-ooxml"

    @property
    def version(self) -> str:
        return "1.0.0"

    def supports(self, mime_type: str) -> bool:
        return mime_type == XLSX_MIME

    def extract(self, content: bytes, mime_type: str) -> QuoteDocumentExtractionResult:
        if not self.supports(mime_type):
            raise QuoteExtractionFailure("XLSX quote extractor received an unsupported MIME type.")
        started = time.perf_counter()
        with ZipFile(BytesIO(content)) as archive:
            shared: list[str] = []
            if "xl/sharedStrings.xml" in archive.namelist():
                root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                for entry in root.findall(f"{_NS_MAIN}si"):
                    shared.append("".join(node.text or "" for node in entry.iter(f"{_NS_MAIN}t")))
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            targets = {
                rel.attrib["Id"]: rel.attrib["Target"]
                for rel in rels.findall("r:Relationship", _REL_NS)
            }
            segments: list[QuoteDocumentSegment] = []
            for ordinal, sheet in enumerate(workbook.find(f"{_NS_MAIN}sheets") or [], start=1):
                name = sheet.attrib.get("name", f"Sheet {ordinal}")
                rel_id = sheet.attrib.get(f"{_NS_REL}id")
                target = targets.get(rel_id or "")
                if not target:
                    continue
                path = target.lstrip("/")
                if not path.startswith("xl/"):
                    path = "xl/" + path
                root = ET.fromstring(archive.read(path))
                rows: list[tuple[str, ...]] = []
                lines: list[str] = []
                for row in root.iter(f"{_NS_MAIN}row"):
                    values: list[str] = []
                    for cell in row.findall(f"{_NS_MAIN}c"):
                        value_node = cell.find(f"{_NS_MAIN}v")
                        value = value_node.text if value_node is not None else ""
                        if cell.attrib.get("t") == "s" and value:
                            try:
                                value = shared[int(value)]
                            except (ValueError, IndexError):
                                value = ""
                        elif cell.attrib.get("t") == "inlineStr":
                            value = "".join(n.text or "" for n in cell.iter(f"{_NS_MAIN}t"))
                        values.append(value or "")
                    if any(value.strip() for value in values):
                        rows.append(tuple(values))
                        lines.append(" | ".join(values))
                segments.append(
                    QuoteDocumentSegment(
                        ordinal=ordinal,
                        location_type="sheet",
                        location_label=name,
                        text="\n".join(lines),
                        tables=(tuple(rows),) if rows else (),
                        method="ooxml-values-only",
                    )
                )
        duration = round((time.perf_counter() - started) * 1000)
        return QuoteDocumentExtractionResult(
            self.name, self.version, tuple(segments), duration, {"sheets": len(segments)}
        )


class DocxQuoteDocumentExtractor(QuoteDocumentExtractor):
    @property
    def name(self) -> str:
        return "docx-ooxml"

    @property
    def version(self) -> str:
        return "1.0.0"

    def supports(self, mime_type: str) -> bool:
        return mime_type == DOCX_MIME

    def extract(self, content: bytes, mime_type: str) -> QuoteDocumentExtractionResult:
        if not self.supports(mime_type):
            raise QuoteExtractionFailure("DOCX quote extractor received an unsupported MIME type.")
        started = time.perf_counter()
        with ZipFile(BytesIO(content)) as archive:
            root = ET.fromstring(archive.read("word/document.xml"))
            lines: list[str] = []
            tables: list[tuple[tuple[str, ...], ...]] = []
            for paragraph in root.iter(f"{_NS_DOC}p"):
                text = "".join(node.text or "" for node in paragraph.iter(f"{_NS_DOC}t")).strip()
                if text:
                    lines.append(text)
            for table in root.iter(f"{_NS_DOC}tbl"):
                rows: list[tuple[str, ...]] = []
                for row in table.findall(f"{_NS_DOC}tr"):
                    cells = tuple(
                        "".join(node.text or "" for node in cell.iter(f"{_NS_DOC}t")).strip()
                        for cell in row.findall(f"{_NS_DOC}tc")
                    )
                    if any(cells):
                        rows.append(cells)
                if rows:
                    tables.append(tuple(rows))
            segment = QuoteDocumentSegment(
                ordinal=1,
                location_type="document",
                location_label="document",
                text="\n".join(lines),
                tables=tuple(tables),
                method="ooxml-text",
            )
        duration = round((time.perf_counter() - started) * 1000)
        return QuoteDocumentExtractionResult(
            self.name, self.version, (segment,), duration, {"tables": len(tables)}
        )


class CompositeQuoteDocumentExtractor(QuoteDocumentExtractor):
    def __init__(self, *extractors: QuoteDocumentExtractor) -> None:
        self._extractors = extractors

    @property
    def name(self) -> str:
        return "quote-document-composite"

    @property
    def version(self) -> str:
        return "+".join(f"{item.name}:{item.version}" for item in self._extractors)

    def supports(self, mime_type: str) -> bool:
        return any(item.supports(mime_type) for item in self._extractors)

    def extract(self, content: bytes, mime_type: str) -> QuoteDocumentExtractionResult:
        for extractor in self._extractors:
            if extractor.supports(mime_type):
                return extractor.extract(content, mime_type)
        raise QuoteExtractionFailure(f"No quote extractor supports {mime_type}.")
