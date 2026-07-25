from uuid import uuid4

from app.application.services.document_quality import (
    DocumentQualityEvaluator,
    QualityThresholds,
)
from app.domain.documents.processing import DocumentPage
from app.domain.documents.value_objects import DocumentQualityDecision


def page(text: str, number: int = 1) -> DocumentPage:
    return DocumentPage(
        document_id=uuid4(),
        extraction_run_id=uuid4(),
        page_number=number,
        text=text,
        width=612,
        height=792,
        duration_ms=1,
    )


def test_quality_evaluator_marks_text_rich_document_ready() -> None:
    evaluator = DocumentQualityEvaluator(QualityThresholds())
    pages = [page("Procurement requirements and technical conditions. " * 20)]
    quality = evaluator.evaluate(uuid4(), uuid4(), pages)
    assert quality.decision is DocumentQualityDecision.READY_FOR_AI
    assert quality.empty_pages == 0
    assert quality.characters_extracted > 200


def test_quality_evaluator_marks_blank_document_for_ocr() -> None:
    evaluator = DocumentQualityEvaluator(QualityThresholds())
    quality = evaluator.evaluate(uuid4(), uuid4(), [page("")])
    assert quality.decision is DocumentQualityDecision.NEEDS_OCR
    assert quality.empty_page_percentage == 100.0


def test_quality_evaluator_marks_borderline_document_for_manual_review() -> None:
    evaluator = DocumentQualityEvaluator(
        QualityThresholds(
            ready_minimum_characters=500,
            ocr_maximum_characters=10,
            ocr_minimum_empty_page_percentage=90,
            ocr_maximum_density=0.01,
        )
    )
    quality = evaluator.evaluate(uuid4(), uuid4(), [page("Reviewable text " * 8)])
    assert quality.decision is DocumentQualityDecision.MANUAL_REVIEW
    assert quality.requires_manual_review is True
