from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.catalog.entities import AIExtractionRun, CatalogProduct, CatalogSnapshot
from app.domain.catalog.exceptions import InvalidProductState
from app.domain.catalog.value_objects import ConfidenceScore, ProductStatus
from app.domain.shared.exceptions import ValidationError


def make_product() -> CatalogProduct:
    return CatalogProduct(
        tender_id=uuid4(),
        ai_extraction_run_id=uuid4(),
        source_document_id=uuid4(),
        original_payload={"name": "  Cable   cobre "},
        name="  Cable   cobre ",
        confidence=ConfidenceScore(0.91),
    )


def test_confidence_and_catalog_snapshot_validation() -> None:
    with pytest.raises(ValidationError):
        ConfidenceScore(1.1)
    with pytest.raises(ValidationError):
        CatalogSnapshot(uuid4(), 0, uuid4(), ({"name": "x"},))
    with pytest.raises(ValidationError):
        CatalogSnapshot(uuid4(), 1, uuid4(), ())


def test_product_state_machine_edit_approve_and_original_evidence_preserved() -> None:
    product = make_product()
    original = dict(product.original_payload)
    product.apply_normalization(
        name="Cable cobre",
        description="Conductor eléctrico",
        quantity=Decimal("1000"),
        unit="m",
        category="Eléctrico",
        specifications={"Calibre": "2 AWG"},
        observations=None,
    )
    assert product.status is ProductStatus.NORMALIZED
    product.start_review()
    reviewer = uuid4()
    product.edit(reviewer_user_id=reviewer, name="Cable de cobre", quantity=Decimal("1200"))
    assert product.manual_edit_count == 1
    assert product.original_payload == original
    product.approve(reviewer)
    assert product.status is ProductStatus.APPROVED
    with pytest.raises(InvalidProductState):
        product.reject(reviewer, "late")


def test_product_rejection_requires_review_and_reason() -> None:
    product = make_product()
    with pytest.raises(InvalidProductState):
        product.approve(uuid4())
    product.apply_normalization(
        name=product.name,
        description=None,
        quantity=None,
        unit=None,
        category=None,
        specifications={},
        observations=None,
    )
    product.start_review()
    with pytest.raises(ValidationError):
        product.reject(uuid4(), " ")
    product.reject(uuid4(), "No corresponde a la licitación")
    assert product.status is ProductStatus.REJECTED


def test_ai_run_lifecycle_records_usage_cost_and_validation_failure() -> None:
    run = AIExtractionRun(
        tender_id=uuid4(),
        document_id=uuid4(),
        idempotency_key="a" * 64,
        prompt_version="1.0.0",
        model="test-model",
        temperature=0,
        schema_version="1.0.0",
        schema_hash="b" * 64,
    )
    run.start()
    run.complete(
        provider_response_id="resp_1",
        input_tokens=100,
        output_tokens=50,
        estimated_cost_usd=Decimal("0.0025"),
        duration_ms=125,
        products_detected=2,
        raw_response={"products": []},
    )
    assert run.status.value == "completed"
    assert run.estimated_cost_usd == Decimal("0.0025")
    failed = AIExtractionRun(
        tender_id=uuid4(),
        document_id=uuid4(),
        idempotency_key="c" * 64,
        prompt_version="1.0.0",
        model="test-model",
        temperature=0,
        schema_version="1.0.0",
        schema_hash="d" * 64,
    )
    failed.fail(ValueError("bad json"), validation_errors=["products.0.name required"])
    assert failed.status.value == "failed"
    assert failed.invalid_json_count == 1
