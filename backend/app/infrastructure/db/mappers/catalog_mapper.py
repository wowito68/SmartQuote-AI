from decimal import Decimal

from app.domain.catalog.entities import (
    AIExtractionRun,
    CatalogProduct,
    CatalogSnapshot,
    EvidenceReference,
    ExtractedEvidence,
)
from app.domain.catalog.value_objects import (
    AIExtractionRunStatus,
    ConfidenceScore,
    ProductQuantity,
    ProductStatus,
)
from app.infrastructure.db.models.catalog import (
    AIExtractionRunModel,
    CatalogProductModel,
    CatalogSnapshotModel,
    EvidenceReferenceModel,
    ExtractedEvidenceModel,
)


def ai_run_to_model(run: AIExtractionRun) -> AIExtractionRunModel:
    return AIExtractionRunModel(
        id=run.id,
        tender_id=run.tender_id,
        document_id=run.document_id,
        idempotency_key=run.idempotency_key,
        prompt_version=run.prompt_version,
        model=run.model,
        temperature=run.temperature,
        schema_version=run.schema_version,
        schema_hash=run.schema_hash,
        status=run.status.value,
        provider_response_id=run.provider_response_id,
        input_tokens=run.input_tokens,
        output_tokens=run.output_tokens,
        estimated_cost_usd=run.estimated_cost_usd,
        duration_ms=run.duration_ms,
        products_detected=run.products_detected,
        invalid_json_count=run.invalid_json_count,
        raw_response=run.raw_response,
        validation_errors=run.validation_errors,
        error_type=run.error_type,
        error_message=run.error_message,
        reused_from_run_id=run.reused_from_run_id,
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
    )


def ai_run_to_domain(model: AIExtractionRunModel) -> AIExtractionRun:
    return AIExtractionRun(
        id=model.id,
        tender_id=model.tender_id,
        document_id=model.document_id,
        idempotency_key=model.idempotency_key,
        prompt_version=model.prompt_version,
        model=model.model,
        temperature=model.temperature,
        schema_version=model.schema_version,
        schema_hash=model.schema_hash,
        status=AIExtractionRunStatus(model.status),
        provider_response_id=model.provider_response_id,
        input_tokens=model.input_tokens,
        output_tokens=model.output_tokens,
        estimated_cost_usd=Decimal(model.estimated_cost_usd),
        duration_ms=model.duration_ms,
        products_detected=model.products_detected,
        invalid_json_count=model.invalid_json_count,
        raw_response=model.raw_response,
        validation_errors=list(model.validation_errors or []),
        error_type=model.error_type,
        error_message=model.error_message,
        reused_from_run_id=model.reused_from_run_id,
        started_at=model.started_at,
        completed_at=model.completed_at,
        created_at=model.created_at,
    )


def update_ai_run_model(model: AIExtractionRunModel, run: AIExtractionRun) -> None:
    model.status = run.status.value
    model.provider_response_id = run.provider_response_id
    model.input_tokens = run.input_tokens
    model.output_tokens = run.output_tokens
    model.estimated_cost_usd = run.estimated_cost_usd
    model.duration_ms = run.duration_ms
    model.products_detected = run.products_detected
    model.invalid_json_count = run.invalid_json_count
    model.raw_response = run.raw_response
    model.validation_errors = run.validation_errors
    model.error_type = run.error_type
    model.error_message = run.error_message
    model.reused_from_run_id = run.reused_from_run_id
    model.started_at = run.started_at
    model.completed_at = run.completed_at


def product_to_model(product: CatalogProduct) -> CatalogProductModel:
    return CatalogProductModel(
        id=product.id,
        tender_id=product.tender_id,
        ai_extraction_run_id=product.ai_extraction_run_id,
        source_document_id=product.source_document_id,
        original_payload=product.original_payload,
        item_number=product.item_number,
        name=product.name,
        description=product.description,
        quantity=product.quantity.value if product.quantity else None,
        unit=product.unit,
        category=product.category,
        specifications=product.specifications,
        observations=product.observations,
        confidence=product.confidence.value,
        status=product.status.value,
        duplicate_of_product_id=product.duplicate_of_product_id,
        manual_edit_count=product.manual_edit_count,
        reviewed_by_user_id=product.reviewed_by_user_id,
        reviewed_at=product.reviewed_at,
        rejection_reason=product.rejection_reason,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


def product_to_domain(model: CatalogProductModel) -> CatalogProduct:
    return CatalogProduct(
        id=model.id,
        tender_id=model.tender_id,
        ai_extraction_run_id=model.ai_extraction_run_id,
        source_document_id=model.source_document_id,
        original_payload=model.original_payload,
        item_number=model.item_number,
        name=model.name,
        description=model.description,
        quantity=ProductQuantity(Decimal(model.quantity)) if model.quantity is not None else None,
        unit=model.unit,
        category=model.category,
        specifications=dict(model.specifications or {}),
        observations=model.observations,
        confidence=ConfidenceScore(model.confidence),
        status=ProductStatus(model.status),
        duplicate_of_product_id=model.duplicate_of_product_id,
        manual_edit_count=model.manual_edit_count,
        reviewed_by_user_id=model.reviewed_by_user_id,
        reviewed_at=model.reviewed_at,
        rejection_reason=model.rejection_reason,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def update_product_model(model: CatalogProductModel, product: CatalogProduct) -> None:
    model.item_number = product.item_number
    model.name = product.name
    model.description = product.description
    model.quantity = product.quantity.value if product.quantity else None
    model.unit = product.unit
    model.category = product.category
    model.specifications = product.specifications
    model.observations = product.observations
    model.status = product.status.value
    model.duplicate_of_product_id = product.duplicate_of_product_id
    model.manual_edit_count = product.manual_edit_count
    model.reviewed_by_user_id = product.reviewed_by_user_id
    model.reviewed_at = product.reviewed_at
    model.rejection_reason = product.rejection_reason
    model.updated_at = product.updated_at


def evidence_to_models(
    evidence: ExtractedEvidence, reference: EvidenceReference
) -> tuple[ExtractedEvidenceModel, EvidenceReferenceModel]:
    return (
        ExtractedEvidenceModel(
            id=evidence.id,
            product_id=evidence.product_id,
            ai_extraction_run_id=evidence.ai_extraction_run_id,
            document_id=evidence.document_id,
            page_number=evidence.page_number,
            text_fragment=evidence.text_fragment,
            confidence=evidence.confidence.value,
            model=evidence.model,
            prompt_version=evidence.prompt_version,
            created_at=evidence.created_at,
        ),
        EvidenceReferenceModel(
            id=reference.id,
            evidence_id=reference.evidence_id,
            page_number=reference.page_number,
            x0=reference.x0,
            y0=reference.y0,
            x1=reference.x1,
            y1=reference.y1,
        ),
    )


def evidence_to_domain(
    evidence: ExtractedEvidenceModel, reference: EvidenceReferenceModel
) -> tuple[ExtractedEvidence, EvidenceReference]:
    return (
        ExtractedEvidence(
            id=evidence.id,
            product_id=evidence.product_id,
            ai_extraction_run_id=evidence.ai_extraction_run_id,
            document_id=evidence.document_id,
            page_number=evidence.page_number,
            text_fragment=evidence.text_fragment,
            confidence=ConfidenceScore(evidence.confidence),
            model=evidence.model,
            prompt_version=evidence.prompt_version,
            created_at=evidence.created_at,
        ),
        EvidenceReference(
            id=reference.id,
            evidence_id=reference.evidence_id,
            page_number=reference.page_number,
            x0=reference.x0,
            y0=reference.y0,
            x1=reference.x1,
            y1=reference.y1,
        ),
    )


def snapshot_to_model(snapshot: CatalogSnapshot) -> CatalogSnapshotModel:
    return CatalogSnapshotModel(
        id=snapshot.id,
        tender_id=snapshot.tender_id,
        version=snapshot.version,
        approved_by_user_id=snapshot.approved_by_user_id,
        products=list(snapshot.products),
        created_at=snapshot.created_at,
    )


def snapshot_to_domain(model: CatalogSnapshotModel) -> CatalogSnapshot:
    return CatalogSnapshot(
        id=model.id,
        tender_id=model.tender_id,
        version=model.version,
        approved_by_user_id=model.approved_by_user_id,
        products=tuple(model.products),
        created_at=model.created_at,
    )
