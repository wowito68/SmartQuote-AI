from uuid import uuid4

import pytest

from app.domain.documents.entities import TenderDocument
from app.domain.documents.exceptions import InvalidDocumentState
from app.domain.documents.processing import DocumentPage
from app.domain.documents.value_objects import DocumentStatus, FileHash


def document() -> TenderDocument:
    return TenderDocument(
        tender_id=uuid4(),
        original_file_name="bases.pdf",
        storage_key=f"tenders/{uuid4()}/{uuid4()}.pdf",
        mime_type="application/pdf",
        file_size=100,
        file_hash=FileHash("a" * 64),
        uploaded_by_user_id=uuid4(),
    )


def test_document_valid_processing_lifecycle() -> None:
    item = document()
    item.mark_queued()
    item.start_processing()
    item.mark_text_extracted()
    item.mark_ready_for_ai()
    assert item.status is DocumentStatus.READY_FOR_AI
    assert item.queued_at is not None
    assert item.processing_started_at is not None
    assert item.processed_at is not None
    assert item.requires_ocr is False


def test_document_invalid_transition_is_rejected() -> None:
    item = document()
    with pytest.raises(InvalidDocumentState):
        item.mark_ready_for_ai()


def test_failed_document_can_be_requeued() -> None:
    item = document()
    item.mark_queued()
    item.start_processing()
    item.mark_failed("extractor crashed")
    assert item.status is DocumentStatus.FAILED
    item.mark_queued()
    assert item.status is DocumentStatus.QUEUED
    assert item.last_processing_error is None


def test_document_page_metrics_are_derived_from_text() -> None:
    page = DocumentPage(
        document_id=uuid4(),
        extraction_run_id=uuid4(),
        page_number=1,
        text="one two three",
        width=612,
        height=792,
        duration_ms=4,
    )
    assert page.character_count == 13
    assert page.word_count == 3
    assert page.is_empty is False
    assert page.text_density > 0
