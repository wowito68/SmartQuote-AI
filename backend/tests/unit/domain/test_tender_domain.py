from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.domain.shared.exceptions import ValidationError
from app.domain.tenders.entities import (
    DESCRIPTION_MAX_LENGTH,
    TITLE_MAX_LENGTH,
    Tender,
)
from app.domain.tenders.exceptions import (
    InvalidDeadline,
    InvalidTenderState,
    TenderAlreadyArchived,
)
from app.domain.tenders.value_objects import TenderStatus


def test_tender_normalizes_required_values() -> None:
    tender = Tender(
        title="  Office supplies  ",
        description="  Annual purchase  ",
        created_by_user_id=uuid4(),
    )
    assert tender.title == "Office supplies"
    assert tender.description == "Annual purchase"
    assert tender.status is TenderStatus.DRAFT


@pytest.mark.parametrize("title", ["", "   ", "x" * (TITLE_MAX_LENGTH + 1)])
def test_tender_rejects_invalid_title(title: str) -> None:
    with pytest.raises(ValidationError):
        Tender(title=title, created_by_user_id=uuid4())


def test_tender_rejects_long_description() -> None:
    with pytest.raises(ValidationError):
        Tender(
            title="Valid",
            description="x" * (DESCRIPTION_MAX_LENGTH + 1),
            created_by_user_id=uuid4(),
        )


def test_deadline_cannot_be_before_creation() -> None:
    created_at = datetime.now(UTC)
    with pytest.raises(InvalidDeadline):
        Tender(
            title="Valid",
            created_by_user_id=uuid4(),
            created_at=created_at,
            deadline=created_at - timedelta(seconds=1),
        )


def test_valid_status_transitions_are_forward_only() -> None:
    tender = Tender(title="Valid", created_by_user_id=uuid4())
    tender.change_status(TenderStatus.DOCUMENTS_PENDING)
    tender.change_status(TenderStatus.DOCUMENTS_PROCESSING)
    tender.change_status(TenderStatus.CATALOG_REVIEW)
    tender.change_status(TenderStatus.CLOSED)
    assert tender.status is TenderStatus.CLOSED
    with pytest.raises(InvalidTenderState):
        tender.change_status(TenderStatus.DRAFT)


def test_archived_tender_cannot_be_modified_or_archived_twice() -> None:
    tender = Tender(title="Valid", created_by_user_id=uuid4())
    tender.archive()
    with pytest.raises(TenderAlreadyArchived):
        tender.replace_details(
            title="New",
            description=None,
            deadline=None,
            status=TenderStatus.DRAFT,
        )
    with pytest.raises(TenderAlreadyArchived):
        tender.archive()


def test_tender_status_rejects_unknown_value() -> None:
    with pytest.raises(ValueError):
        TenderStatus("unknown")
