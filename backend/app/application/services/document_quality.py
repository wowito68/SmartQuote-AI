from dataclasses import dataclass
from uuid import UUID

from app.domain.documents.processing import DocumentPage, DocumentQuality
from app.domain.documents.value_objects import (
    DocumentQualityDecision,
    DocumentQualityLevel,
)


@dataclass(frozen=True, slots=True)
class QualityThresholds:
    ready_minimum_characters: int = 200
    ready_maximum_empty_page_percentage: float = 25.0
    ready_minimum_density: float = 1.5
    ocr_maximum_characters: int = 50
    ocr_minimum_empty_page_percentage: float = 50.0
    ocr_maximum_density: float = 0.5

    def as_dict(self) -> dict[str, int | float]:
        return {
            "ready_minimum_characters": self.ready_minimum_characters,
            "ready_maximum_empty_page_percentage": self.ready_maximum_empty_page_percentage,
            "ready_minimum_density": self.ready_minimum_density,
            "ocr_maximum_characters": self.ocr_maximum_characters,
            "ocr_minimum_empty_page_percentage": self.ocr_minimum_empty_page_percentage,
            "ocr_maximum_density": self.ocr_maximum_density,
        }


class DocumentQualityEvaluator:
    def __init__(self, thresholds: QualityThresholds) -> None:
        self.thresholds = thresholds

    def evaluate(
        self,
        document_id: UUID,
        extraction_run_id: UUID,
        pages: list[DocumentPage],
    ) -> DocumentQuality:
        page_count = len(pages)
        empty_pages = sum(page.is_empty for page in pages)
        characters = sum(page.character_count for page in pages)
        empty_percentage = (empty_pages / page_count * 100.0) if page_count else 100.0
        total_area = sum((page.width * page.height) / (72.0 * 72.0) for page in pages)
        density = characters / max(total_area, 1.0)

        if (
            page_count > 0
            and characters >= self.thresholds.ready_minimum_characters
            and empty_percentage <= self.thresholds.ready_maximum_empty_page_percentage
            and density >= self.thresholds.ready_minimum_density
        ):
            level = DocumentQualityLevel.HIGH
            decision = DocumentQualityDecision.READY_FOR_AI
            manual_review = False
        elif (
            page_count == 0
            or characters <= self.thresholds.ocr_maximum_characters
            or empty_percentage >= self.thresholds.ocr_minimum_empty_page_percentage
            or density <= self.thresholds.ocr_maximum_density
        ):
            level = DocumentQualityLevel.LOW
            decision = DocumentQualityDecision.NEEDS_OCR
            manual_review = False
        else:
            level = DocumentQualityLevel.MEDIUM
            decision = DocumentQualityDecision.MANUAL_REVIEW
            manual_review = True

        return DocumentQuality(
            document_id=document_id,
            extraction_run_id=extraction_run_id,
            pages_processed=page_count,
            empty_pages=empty_pages,
            characters_extracted=characters,
            empty_page_percentage=round(empty_percentage, 4),
            text_density=round(density, 6),
            quality_level=level,
            decision=decision,
            requires_manual_review=manual_review,
        )
