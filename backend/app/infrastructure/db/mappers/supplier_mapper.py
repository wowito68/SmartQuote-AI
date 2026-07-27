from app.domain.suppliers.entities import (
    ProductSupplierMatch,
    Supplier,
    SupplierContact,
    SupplierDiscoveryRun,
    SupplierMergeSuggestion,
    SupplierSource,
    TenderSupplier,
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
from app.infrastructure.db.models.supplier import (
    ProductSupplierMatchModel,
    SupplierContactModel,
    SupplierDiscoveryRunModel,
    SupplierMergeSuggestionModel,
    SupplierModel,
    SupplierSourceModel,
    TenderSupplierModel,
)


def discovery_run_to_model(run: SupplierDiscoveryRun) -> SupplierDiscoveryRunModel:
    return SupplierDiscoveryRunModel(
        id=run.id,
        tender_id=run.tender_id,
        catalog_snapshot_id=run.catalog_snapshot_id,
        requested_by_user_id=run.requested_by_user_id,
        idempotency_key=run.idempotency_key,
        search_provider=run.search_provider,
        search_provider_version=run.search_provider_version,
        search_configuration=run.search_configuration,
        matching_algorithm_version=run.matching_algorithm_version,
        status=run.status.value,
        current_stage=run.current_stage.value,
        raw_candidates=run.raw_candidates,
        processed_candidates=run.processed_candidates,
        suppliers_found=run.suppliers_found,
        duplicates_detected=run.duplicates_detected,
        contacts_found=run.contacts_found,
        provider_errors=run.provider_errors,
        search_duration_ms=run.search_duration_ms,
        matching_duration_ms=run.matching_duration_ms,
        error_type=run.error_type,
        error_message=run.error_message,
        reused_from_run_id=run.reused_from_run_id,
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
    )


def discovery_run_to_domain(model: SupplierDiscoveryRunModel) -> SupplierDiscoveryRun:
    return SupplierDiscoveryRun(
        id=model.id,
        tender_id=model.tender_id,
        catalog_snapshot_id=model.catalog_snapshot_id,
        requested_by_user_id=model.requested_by_user_id,
        idempotency_key=model.idempotency_key,
        search_provider=model.search_provider,
        search_provider_version=model.search_provider_version,
        search_configuration=model.search_configuration,
        matching_algorithm_version=model.matching_algorithm_version,
        status=SupplierDiscoveryRunStatus(model.status),
        current_stage=SupplierDiscoveryStage(model.current_stage),
        raw_candidates=list(model.raw_candidates or []),
        processed_candidates=list(model.processed_candidates or []),
        suppliers_found=model.suppliers_found,
        duplicates_detected=model.duplicates_detected,
        contacts_found=model.contacts_found,
        provider_errors=list(model.provider_errors or []),
        search_duration_ms=model.search_duration_ms,
        matching_duration_ms=model.matching_duration_ms,
        error_type=model.error_type,
        error_message=model.error_message,
        reused_from_run_id=model.reused_from_run_id,
        started_at=model.started_at,
        completed_at=model.completed_at,
        created_at=model.created_at,
    )


def update_discovery_run_model(
    model: SupplierDiscoveryRunModel, run: SupplierDiscoveryRun
) -> None:
    model.status = run.status.value
    model.current_stage = run.current_stage.value
    model.raw_candidates = run.raw_candidates
    model.processed_candidates = run.processed_candidates
    model.suppliers_found = run.suppliers_found
    model.duplicates_detected = run.duplicates_detected
    model.contacts_found = run.contacts_found
    model.provider_errors = run.provider_errors
    model.search_duration_ms = run.search_duration_ms
    model.matching_duration_ms = run.matching_duration_ms
    model.error_type = run.error_type
    model.error_message = run.error_message
    model.reused_from_run_id = run.reused_from_run_id
    model.started_at = run.started_at
    model.completed_at = run.completed_at


def supplier_to_model(supplier: Supplier) -> SupplierModel:
    return SupplierModel(
        id=supplier.id,
        legal_name=supplier.legal_name,
        trade_name=supplier.trade_name,
        website=supplier.website,
        normalized_domain=supplier.normalized_domain,
        category=supplier.category,
        country=supplier.country,
        city=supplier.city,
        description=supplier.description,
        merged_into_supplier_id=supplier.merged_into_supplier_id,
        created_at=supplier.created_at,
        updated_at=supplier.updated_at,
    )


def supplier_to_domain(model: SupplierModel) -> Supplier:
    return Supplier(
        id=model.id,
        legal_name=model.legal_name,
        trade_name=model.trade_name,
        website=model.website,
        normalized_domain=model.normalized_domain,
        category=model.category,
        country=model.country,
        city=model.city,
        description=model.description,
        merged_into_supplier_id=model.merged_into_supplier_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def update_supplier_model(model: SupplierModel, supplier: Supplier) -> None:
    model.legal_name = supplier.legal_name
    model.trade_name = supplier.trade_name
    model.website = supplier.website
    model.normalized_domain = supplier.normalized_domain
    model.category = supplier.category
    model.country = supplier.country
    model.city = supplier.city
    model.description = supplier.description
    model.merged_into_supplier_id = supplier.merged_into_supplier_id
    model.updated_at = supplier.updated_at


def contact_to_model(contact: SupplierContact) -> SupplierContactModel:
    return SupplierContactModel(
        id=contact.id,
        supplier_id=contact.supplier_id,
        contact_type=contact.contact_type.value,
        value=contact.value,
        identity_key=contact.identity_key,
        confidence=contact.confidence.value,
        source_url=contact.source_url,
        contact_name=contact.contact_name,
        role=contact.role,
        created_at=contact.created_at,
    )


def contact_to_domain(model: SupplierContactModel) -> SupplierContact:
    return SupplierContact(
        id=model.id,
        supplier_id=model.supplier_id,
        contact_type=SupplierContactType(model.contact_type),
        value=model.value,
        confidence=SupplierConfidence(model.confidence),
        source_url=model.source_url,
        contact_name=model.contact_name,
        role=model.role,
        created_at=model.created_at,
    )


def source_to_model(source: SupplierSource) -> SupplierSourceModel:
    return SupplierSourceModel(
        id=source.id,
        supplier_id=source.supplier_id,
        provider_name=source.provider_name,
        source_type=source.source_type,
        source_url=source.source_url,
        source_title=source.source_title,
        excerpt=source.excerpt,
        discovered_at=source.discovered_at,
    )


def source_to_domain(model: SupplierSourceModel) -> SupplierSource:
    return SupplierSource(
        id=model.id,
        supplier_id=model.supplier_id,
        provider_name=model.provider_name,
        source_type=model.source_type,
        source_url=model.source_url,
        source_title=model.source_title,
        excerpt=model.excerpt,
        discovered_at=model.discovered_at,
    )


def tender_supplier_to_model(item: TenderSupplier) -> TenderSupplierModel:
    return TenderSupplierModel(
        id=item.id,
        tender_id=item.tender_id,
        supplier_id=item.supplier_id,
        discovery_run_id=item.discovery_run_id,
        status=item.status.value,
        is_manual=item.is_manual,
        reviewed_by_user_id=item.reviewed_by_user_id,
        reviewed_at=item.reviewed_at,
        rejection_reason=item.rejection_reason,
        merged_into_tender_supplier_id=item.merged_into_tender_supplier_id,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def tender_supplier_to_domain(model: TenderSupplierModel) -> TenderSupplier:
    return TenderSupplier(
        id=model.id,
        tender_id=model.tender_id,
        supplier_id=model.supplier_id,
        discovery_run_id=model.discovery_run_id,
        status=SupplierStatus(model.status),
        is_manual=model.is_manual,
        reviewed_by_user_id=model.reviewed_by_user_id,
        reviewed_at=model.reviewed_at,
        rejection_reason=model.rejection_reason,
        merged_into_tender_supplier_id=model.merged_into_tender_supplier_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def update_tender_supplier_model(model: TenderSupplierModel, item: TenderSupplier) -> None:
    model.status = item.status.value
    model.reviewed_by_user_id = item.reviewed_by_user_id
    model.reviewed_at = item.reviewed_at
    model.rejection_reason = item.rejection_reason
    model.merged_into_tender_supplier_id = item.merged_into_tender_supplier_id
    model.updated_at = item.updated_at


def match_to_model(match: ProductSupplierMatch) -> ProductSupplierMatchModel:
    return ProductSupplierMatchModel(
        id=match.id,
        tender_supplier_id=match.tender_supplier_id,
        product_id=match.product_id,
        score=match.score.value,
        components=match.components,
        reasons=list(match.reasons),
        algorithm_version=match.algorithm_version,
        created_at=match.created_at,
    )


def match_to_domain(model: ProductSupplierMatchModel) -> ProductSupplierMatch:
    return ProductSupplierMatch(
        id=model.id,
        tender_supplier_id=model.tender_supplier_id,
        product_id=model.product_id,
        score=SupplierMatchScore(model.score),
        components=dict(model.components or {}),
        reasons=tuple(model.reasons or []),
        algorithm_version=model.algorithm_version,
        created_at=model.created_at,
    )


def update_match_model(model: ProductSupplierMatchModel, match: ProductSupplierMatch) -> None:
    model.score = match.score.value
    model.components = match.components
    model.reasons = list(match.reasons)
    model.algorithm_version = match.algorithm_version


def merge_suggestion_to_model(
    suggestion: SupplierMergeSuggestion,
) -> SupplierMergeSuggestionModel:
    return SupplierMergeSuggestionModel(
        id=suggestion.id,
        source_supplier_id=suggestion.source_supplier_id,
        target_supplier_id=suggestion.target_supplier_id,
        discovery_run_id=suggestion.discovery_run_id,
        score=suggestion.score.value,
        signals=list(suggestion.signals),
        status=suggestion.status.value,
        reviewed_by_user_id=suggestion.reviewed_by_user_id,
        reviewed_at=suggestion.reviewed_at,
        created_at=suggestion.created_at,
    )


def merge_suggestion_to_domain(
    model: SupplierMergeSuggestionModel,
) -> SupplierMergeSuggestion:
    return SupplierMergeSuggestion(
        id=model.id,
        source_supplier_id=model.source_supplier_id,
        target_supplier_id=model.target_supplier_id,
        discovery_run_id=model.discovery_run_id,
        score=SupplierConfidence(model.score),
        signals=tuple(model.signals or []),
        status=MergeSuggestionStatus(model.status),
        reviewed_by_user_id=model.reviewed_by_user_id,
        reviewed_at=model.reviewed_at,
        created_at=model.created_at,
    )


def update_merge_suggestion_model(
    model: SupplierMergeSuggestionModel, suggestion: SupplierMergeSuggestion
) -> None:
    model.status = suggestion.status.value
    model.reviewed_by_user_id = suggestion.reviewed_by_user_id
    model.reviewed_at = suggestion.reviewed_at
