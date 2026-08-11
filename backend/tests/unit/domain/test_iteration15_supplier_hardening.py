from uuid import uuid4

import pytest

from app.domain.shared.exceptions import ValidationError
from app.domain.suppliers.entities import (
    ProductSupplierMatch,
    Supplier,
    SupplierContact,
    SupplierDiscoveryRun,
    SupplierMergeSuggestion,
    SupplierSource,
    TenderSupplier,
)
from app.domain.suppliers.exceptions import (
    InvalidSupplierDiscoveryState,
    InvalidSupplierState,
    SupplierMergeConflict,
)
from app.domain.suppliers.value_objects import (
    MergeSuggestionStatus,
    SupplierConfidence,
    SupplierContactType,
    SupplierDiscoveryRunStatus,
    SupplierDiscoveryStage,
    SupplierMatchScore,
    SupplierStatus,
)


def _run(**changes) -> SupplierDiscoveryRun:
    values = {
        "tender_id": uuid4(),
        "catalog_snapshot_id": uuid4(),
        "requested_by_user_id": uuid4(),
        "idempotency_key": "e" * 64,
        "search_provider": "mock-search",
        "search_provider_version": "1",
        "search_configuration": {"limit": 10},
        "matching_algorithm_version": "1.0",
    }
    values.update(changes)
    return SupplierDiscoveryRun(**values)


def test_supplier_contact_source_edit_and_merge_guards() -> None:
    with pytest.raises(ValidationError):
        Supplier()
    supplier = Supplier(
        legal_name=" Acme SA ",
        website="https://www.Example.COM/path",
        category=" Sensors ",
        country=" MX ",
        city=" Queretaro ",
    )
    assert supplier.display_name == "Acme SA"
    assert supplier.normalized_domain == "example.com"
    supplier.edit(
        trade_name=" Acme Sensors ",
        website="shop.example.com",
        category="Industrial",
        country="Mexico",
        city="Qro",
        description=" supplier ",
    )
    assert supplier.display_name == "Acme Sensors"
    with pytest.raises(SupplierMergeConflict):
        supplier.merge_into(supplier.id)
    supplier.merge_into(uuid4())
    with pytest.raises(InvalidSupplierState):
        supplier.edit(city="Mexico City")
    with pytest.raises(SupplierMergeConflict):
        supplier.merge_into(uuid4())

    confidence = SupplierConfidence(0.8)
    email = SupplierContact(
        supplier_id=uuid4(),
        contact_type=SupplierContactType.EMAIL,
        value=" SALES@EXAMPLE.COM ",
        confidence=confidence,
        source_url="https://example.com/contact",
    )
    phone = SupplierContact(
        supplier_id=uuid4(),
        contact_type=SupplierContactType.PHONE,
        value="+52 442 123 4567",
        confidence=confidence,
        source_url="manual://user",
    )
    form = SupplierContact(
        supplier_id=uuid4(),
        contact_type=SupplierContactType.CONTACT_FORM,
        value="https://example.com/contact/",
        confidence=confidence,
        source_url="https://example.com",
    )
    assert email.identity_key == "email:sales@example.com"
    assert phone.identity_key.endswith("524421234567")
    assert form.identity_key == "contact_form:https://example.com/contact"
    for contact_type, value in (
        (SupplierContactType.EMAIL, "bad"),
        (SupplierContactType.PHONE, "123"),
        (SupplierContactType.CONTACT_FORM, "not-url"),
    ):
        with pytest.raises(ValidationError):
            SupplierContact(uuid4(), contact_type, value, confidence, "https://source")

    source = SupplierSource(
        supplier_id=uuid4(),
        provider_name="manual",
        source_type="manual",
        source_url="manual://user/1",
        metadata={"a": 1},
    )
    assert source.metadata == {"a": 1}
    with pytest.raises(ValidationError):
        SupplierSource(uuid4(), "search", "result", "ftp://example.com")


def test_tender_supplier_review_reject_and_merge_state_machine() -> None:
    reviewer = uuid4()
    approved = TenderSupplier(tender_id=uuid4(), supplier_id=uuid4())
    approved.mark_contact_discovery_complete()
    approved.start_review()
    approved.approve(reviewer)
    assert approved.status is SupplierStatus.APPROVED
    with pytest.raises(InvalidSupplierState):
        approved.reject(reviewer, "late")

    rejected = TenderSupplier(tender_id=uuid4(), supplier_id=uuid4())
    rejected.mark_contact_discovery_complete()
    rejected.start_review()
    with pytest.raises(ValidationError):
        rejected.reject(reviewer, " ")
    rejected.reject(reviewer, " not qualified ")
    assert rejected.status is SupplierStatus.REJECTED

    merged = TenderSupplier(tender_id=uuid4(), supplier_id=uuid4())
    merged.mark_contact_discovery_complete()
    merged.start_review()
    with pytest.raises(SupplierMergeConflict):
        merged.merge_into(merged.id, reviewer)
    merged.merge_into(uuid4(), reviewer)
    assert merged.status is SupplierStatus.MERGED


def test_supplier_discovery_stage_failure_restart_and_reuse() -> None:
    for changes in (
        {"idempotency_key": "bad"},
        {"search_provider": " "},
        {"matching_algorithm_version": " "},
    ):
        with pytest.raises(ValidationError):
            _run(**changes)

    run = _run()
    with pytest.raises(InvalidSupplierDiscoveryState):
        run.save_search_results([], duration_ms=1, provider_errors=[])
    run.start()
    run.save_search_results(
        [{"name": "Acme"}], duration_ms=-1, provider_errors=["x"] * 101
    )
    assert run.current_stage is SupplierDiscoveryStage.DEDUPLICATION
    assert run.search_duration_ms == 0 and len(run.provider_errors) == 100
    run.save_deduplicated([{"name": "Acme"}], duplicates_detected=-1)
    assert run.duplicates_detected == 0
    run.mark_contacts_complete(-5)
    assert run.contacts_found == 0
    run.mark_matching_complete(-2)
    assert run.current_stage is SupplierDiscoveryStage.REVIEW
    assert run.matching_duration_ms == 0
    run.complete()
    assert run.status is SupplierDiscoveryRunStatus.COMPLETED
    run.start()
    assert run.status is SupplierDiscoveryRunStatus.COMPLETED
    run.fail(RuntimeError("search failed"))
    run.restart()
    source = uuid4()
    run.mark_reused(source)
    assert run.status is SupplierDiscoveryRunStatus.REUSED
    assert run.reused_from_run_id == source


def test_supplier_match_and_merge_suggestion_require_traceable_reasons() -> None:
    match = ProductSupplierMatch(
        tender_supplier_id=uuid4(),
        product_id=uuid4(),
        score=SupplierMatchScore(80),
        components={"name": 1.0},
        reasons=("name match",),
        algorithm_version="1.0",
    )
    assert match.reason == "name match"
    with pytest.raises(ValidationError):
        ProductSupplierMatch(
            uuid4(), uuid4(), SupplierMatchScore(50), {}, (), "1.0"
        )
    with pytest.raises(ValidationError):
        ProductSupplierMatch(
            uuid4(), uuid4(), SupplierMatchScore(50), {}, ("reason",), " "
        )

    source = uuid4()
    target = uuid4()
    suggestion = SupplierMergeSuggestion(
        source,
        target,
        SupplierConfidence(0.9),
        ("same domain",),
    )
    suggestion.accept(uuid4())
    assert suggestion.status is MergeSuggestionStatus.ACCEPTED
    with pytest.raises(SupplierMergeConflict):
        suggestion.reject(uuid4())
    rejected = SupplierMergeSuggestion(
        uuid4(),
        uuid4(),
        SupplierConfidence(0.8),
        ("similar name",),
    )
    rejected.reject(uuid4())
    assert rejected.status is MergeSuggestionStatus.REJECTED
    with pytest.raises(SupplierMergeConflict):
        SupplierMergeSuggestion(source, source, SupplierConfidence(0.9), ("same",))
    with pytest.raises(ValidationError):
        SupplierMergeSuggestion(uuid4(), uuid4(), SupplierConfidence(0.9), ())
