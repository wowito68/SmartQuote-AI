import time
from io import BytesIO
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from app.application.ports.document_text_extractor import DocumentTextExtractor
from app.application.ports.quote_document_extractor import (
    ExtractedQuoteSection,
    QuoteDocumentExtractionResult,
    QuoteDocumentExtractor,
)
from app.domain.quotes.exceptions import QuoteExtractionFailure
from app.domain.quotes.value_objects import QuoteDocumentType


class MultiFormatQuoteDocumentExtractor(QuoteDocumentExtractor):
    OFFICE_VERSION = "ooxml-stdlib-1.0.0"

    def __init__(self, pdf_extractor: DocumentTextExtractor) -> None:
        self._pdf = pdf_extractor

    @property
    def version(self) -> str:
        return f"pdf:{self._pdf.version}|office:{self.OFFICE_VERSION}"

    def extract(
        self,
        document_type: QuoteDocumentType,
        content: bytes,
    ) -> QuoteDocumentExtractionResult:
        if document_type is QuoteDocumentType.PDF:
            return self._extract_pdf(content)
        if document_type is QuoteDocumentType.XLSX:
            return self._extract_xlsx(content)
        if document_type is QuoteDocumentType.DOCX:
            return self._extract_docx(content)
        raise QuoteExtractionFailure(f"Unsupported quote document type: {document_type.value}")

    def _extract_pdf(self, content: bytes) -> QuoteDocumentExtractionResult:
        result = self._pdf.extract(content)
        sections = tuple(
            ExtractedQuoteSection(
                sequence=index,
                locator_type="page",
                locator=f"page:{page.page_number}",
                page_number=page.page_number,
                text=page.text,
                extraction_method=result.extractor_name,
            )
            for index, page in enumerate(result.pages, start=1)
        )
        return QuoteDocumentExtractionResult(
            document_type=QuoteDocumentType.PDF,
            extractor_name=result.extractor_name,
            extractor_version=result.extractor_version,
            sections=sections,
            duration_ms=result.duration_ms,
        )

    @staticmethod
    def _xml(archive: ZipFile, name: str) -> ET.Element:
        try:
            return ET.fromstring(archive.read(name))
        except (KeyError, ET.ParseError) as exc:
            raise QuoteExtractionFailure(f"Office quote XML is invalid: {name}") from exc

    def _extract_xlsx(self, content: bytes) -> QuoteDocumentExtractionResult:
        started = time.perf_counter()
        ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        rel_ns = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
        office_rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
        with ZipFile(BytesIO(content)) as archive:
            names = set(archive.namelist())
            shared: list[str] = []
            if "xl/sharedStrings.xml" in names:
                shared_root = self._xml(archive, "xl/sharedStrings.xml")
                for si in shared_root.findall("m:si", ns):
                    shared.append("".join(node.text or "" for node in si.iter() if node.tag.endswith("}t")))
            workbook = self._xml(archive, "xl/workbook.xml")
            relationships: dict[str, str] = {}
            if "xl/_rels/workbook.xml.rels" in names:
                rel_root = self._xml(archive, "xl/_rels/workbook.xml.rels")
                for rel in rel_root.findall("r:Relationship", rel_ns):
                    relationships[rel.attrib.get("Id", "")] = rel.attrib.get("Target", "")
            sections: list[ExtractedQuoteSection] = []
            sequence = 1
            for sheet_index, sheet in enumerate(workbook.findall("m:sheets/m:sheet", ns), start=1):
                sheet_name = sheet.attrib.get("name", f"Sheet{sheet_index}")
                rel_id = sheet.attrib.get(f"{{{office_rel}}}id", "")
                target = relationships.get(rel_id, f"worksheets/sheet{sheet_index}.xml")
                path = str(PurePosixPath("xl") / target).replace("xl/../", "")
                if path not in names:
                    path = f"xl/worksheets/sheet{sheet_index}.xml"
                root = self._xml(archive, path)
                for row_index, row in enumerate(root.findall(".//m:sheetData/m:row", ns), start=1):
                    cells: list[str] = []
                    for cell in row.findall("m:c", ns):
                        ref = cell.attrib.get("r", "")
                        cell_type = cell.attrib.get("t")
                        value_node = cell.find("m:v", ns)
                        inline = cell.find("m:is", ns)
                        value = ""
                        if cell_type == "s" and value_node is not None:
                            try:
                                value = shared[int(value_node.text or "0")]
                            except (ValueError, IndexError):
                                value = ""
                        elif cell_type == "inlineStr" and inline is not None:
                            value = "".join(node.text or "" for node in inline.iter() if node.tag.endswith("}t"))
                        elif value_node is not None:
                            # Cached values are data only. Formula XML is never evaluated.
                            value = value_node.text or ""
                        if value.strip():
                            cells.append(f"{ref}={value.strip()}")
                    if cells:
                        sections.append(
                            ExtractedQuoteSection(
                                sequence=sequence,
                                locator_type="sheet_row",
                                locator=f"sheet:{sheet_name}:row:{row.attrib.get('r', row_index)}",
                                text=" | ".join(cells),
                                extraction_method="xlsx_ooxml_readonly",
                            )
                        )
                        sequence += 1
        if not sections:
            raise QuoteExtractionFailure("XLSX quote does not contain readable cell data.")
        return QuoteDocumentExtractionResult(
            document_type=QuoteDocumentType.XLSX,
            extractor_name="xlsx-ooxml",
            extractor_version=self.OFFICE_VERSION,
            sections=tuple(sections),
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    def _extract_docx(self, content: bytes) -> QuoteDocumentExtractionResult:
        started = time.perf_counter()
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        with ZipFile(BytesIO(content)) as archive:
            root = self._xml(archive, "word/document.xml")
            body = root.find("w:body", ns)
            if body is None:
                raise QuoteExtractionFailure("DOCX quote does not contain a document body.")
            sections: list[ExtractedQuoteSection] = []
            sequence = 1
            paragraph_index = 0
            table_index = 0
            for child in list(body):
                if child.tag.endswith("}p"):
                    paragraph_index += 1
                    text = " ".join(
                        "".join(node.text or "" for node in child.iter() if node.tag.endswith("}t")).split()
                    )
                    if text:
                        sections.append(
                            ExtractedQuoteSection(
                                sequence=sequence,
                                locator_type="paragraph",
                                locator=f"paragraph:{paragraph_index}",
                                text=text,
                                extraction_method="docx_ooxml_readonly",
                            )
                        )
                        sequence += 1
                elif child.tag.endswith("}tbl"):
                    table_index += 1
                    for row_index, row in enumerate(child.findall("w:tr", ns), start=1):
                        values = []
                        for cell in row.findall("w:tc", ns):
                            value = " ".join(
                                "".join(node.text or "" for node in cell.iter() if node.tag.endswith("}t")).split()
                            )
                            values.append(value)
                        if any(values):
                            sections.append(
                                ExtractedQuoteSection(
                                    sequence=sequence,
                                    locator_type="table_row",
                                    locator=f"table:{table_index}:row:{row_index}",
                                    text=" | ".join(values),
                                    extraction_method="docx_ooxml_readonly",
                                )
                            )
                            sequence += 1
        if not sections:
            raise QuoteExtractionFailure("DOCX quote does not contain readable text or tables.")
        return QuoteDocumentExtractionResult(
            document_type=QuoteDocumentType.DOCX,
            extractor_name="docx-ooxml",
            extractor_version=self.OFFICE_VERSION,
            sections=tuple(sections),
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
