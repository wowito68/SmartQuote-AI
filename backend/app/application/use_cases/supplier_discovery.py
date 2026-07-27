import hashlib
import json
import logging
import time
from typing import Any
from uuid import UUID

from app.application.dtos.suppliers import (
    SupplierDiscoveryRequestResponse,
    SupplierDiscoveryRunResponse,
)
from app.application.exceptions import TenderNotFound
from app.application.ports.supplier_discovery_queue import SupplierDiscoveryQueue
from app.application.ports.supplier_search_service import (
    SupplierContactSuggestion,
    SupplierSearchProduct,
    SupplierSearchRequest,
    SupplierSearchService,
    SupplierSuggestion,
)
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.application.services.supplier_deduplication import SupplierDeduplicationService
from app.application.services.supplier_matching import SupplierMatchingService
from app.domain.catalog.exceptions import InvalidCatalogState
from app.domain.suppliers.entities import (
    ProductSupplierMatch,
    Supplier,
    SupplierContact,
    SupplierDiscoveryRun,
    SupplierMergeSuggestion,
    SupplierSource,
    TenderSupplier,
)
from app.domain.suppliers.events import supplier_event
from app.domain.suppliers.exceptions import (
    SupplierDiscoveryNotFound,
    SupplierDiscoveryQueueFailure,
    SupplierSearchFailure,
)
from app.domain.suppliers.value_objects import (
    SupplierConfidence,
    SupplierContactType,
    SupplierDiscoveryRunStatus,
    SupplierDiscoveryStage,
    SupplierMatchScore,
    SupplierStatus,
)

logger = logging.getLogger(__name__)

_STAGE_ORDER = {
    SupplierDiscoveryStage.QUEUED: 0,
    SupplierDiscoveryStage.SEARCH: 1,
    SupplierDiscoveryStage.DEDUPLICATION: 2,
    SupplierDiscoveryStage.CONTACTS: 3,
    SupplierDiscoveryStage.MATCHING: 4,
    SupplierDiscoveryStage.REVIEW: 5,
    SupplierDiscoveryStage.COMPLETED: 6,
}


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _idempotency_key(
    *,
    snapshot_products: tuple[dict[str, Any], ...],
    search_configuration: dict[str, Any],
    provider_name: str,
    provider_version: str,
    matching_version: str,
) -> str:
    return _canonical_hash(
        {
            "catalog": snapshot_products,
            "search_configuration": search_configuration,
            "provider": provider_name,
            "provider_version": provider_version,
            "matching_version": matching_version,
        }
    )


def _run_response(run: SupplierDiscoveryRun, *, reused: bool) -> SupplierDiscoveryRunResponse:
    return SupplierDiscoveryRunResponse(
        id=run.id,
        tender_id=run.tender_id,
        catalog_snapshot_id=run.catalog_snapshot_id,
        status=run.status,
        current_stage=run.current_stage,
        search_provider=run.search_provider,
        search_provider_version=run.search_provider_version,
        matching_algorithm_version=run.matching_algorithm_version,
        reused=reused,
        created_at=run.created_at,
    )


def _suggestion_payload(product_id: UUID, suggestion: SupplierSuggestion) -> dict[str, Any]:
    return {
        "product_id": str(product_id),
        "legal_name": suggestion.legal_name,
        "trade_name": suggestion.trade_name,
        "website": suggestion.website,
        "category": suggestion.category,
        "country": suggestion.country,
        "city": suggestion.city,
        "description": suggestion.description,
        "source_url": suggestion.source_url,
        "source_title": suggestion.source_title,
        "source_type": suggestion.source_type,
        "source_excerpt": suggestion.source_excerpt,
        "contacts": [
            {
                "contact_type": contact.contact_type,
                "value": contact.value,
                "confidence": contact.confidence,
                "source_url": contact.source_url,
                "contact_name": contact.contact_name,
                "role": contact.role,
            }
            for contact in suggestion.contacts
        ],
        "metadata": suggestion.metadata,
    }


def _suggestion_from_payload(payload: dict[str, Any]) -> SupplierSuggestion:
    return SupplierSuggestion(
        legal_name=payload.get("legal_name"),
        trade_name=payload.get("trade_name"),
        website=payload.get("website"),
        category=payload.get("category"),
        country=payload.get("country"),
        city=payload.get("city"),
        description=payload.get("description"),
        source_url=str(payload.get("source_url") or ""),
        source_title=payload.get("source_title"),
        source_type=str(payload.get("source_type") or "search_result"),
        source_excerpt=payload.get("source_excerpt"),
        contacts=tuple(
            SupplierContactSuggestion(
                contact_type=str(contact.get("contact_type") or ""),
                value=str(contact.get("value") or ""),
                confidence=float(contact.get("confidence", 0.5)),
                source_url=str(contact.get("source_url") or payload.get("source_url") or ""),
                contact_name=contact.get("contact_name"),
                role=contact.get("role"),
            )
            for contact in payload.get("contacts", [])
            if isinstance(contact, dict)
        ),
        metadata=dict(payload.get("metadata") or {}),
    )


class RequestSupplierDiscovery:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        queue: SupplierDiscoveryQueue,
        search_service: SupplierSearchService,
        matching_service: SupplierMatchingService,
        *,
        search_configuration: dict[str, Any],
    ) -> None:
        self._uow_factory = uow_factory
        self._queue = queue
        self._search_service = search_service
        self._matching_service = matching_service
        self._search_configuration = search_configuration

    def execute(
        self, tender_id: UUID, requested_by_user_id: UUID
    ) -> SupplierDiscoveryRequestResponse:
        queued = False
        reused = False
        with self._uow_factory() as uow:
            if uow.tenders.get_by_id(tender_id) is None:
                raise TenderNotFound("Tender was not found.")
            if not uow.users.exists(requested_by_user_id):
                raise InvalidCatalogState("Supplier discovery user was not found.")
            snapshot = uow.catalogs.get_latest_snapshot(tender_id)
            if snapshot is None:
                raise InvalidCatalogState(
                    "Tender requires an approved catalog before supplier discovery."
                )
            key = _idempotency_key(
                snapshot_products=snapshot.products,
                search_configuration=self._search_configuration,
                provider_name=self._search_service.provider_name,
                provider_version=self._search_service.provider_version,
                matching_version=self._matching_service.version,
            )
            existing = uow.suppliers.get_run_by_idempotency(tender_id, key)
            if existing is None:
                run = uow.suppliers.create_run(
                    SupplierDiscoveryRun(
                        tender_id=tender_id,
                        catalog_snapshot_id=snapshot.id,
                        requested_by_user_id=requested_by_user_id,
                        idempotency_key=key,
                        search_provider=self._search_service.provider_name,
                        search_provider_version=self._search_service.provider_version,
                        search_configuration=self._search_configuration,
                        matching_algorithm_version=self._matching_service.version,
                    )
                )
                queued = True
            elif existing.status in {
                SupplierDiscoveryRunStatus.COMPLETED,
                SupplierDiscoveryRunStatus.REUSED,
            }:
                run = existing
                reused = True
            elif existing.status is SupplierDiscoveryRunStatus.FAILED:
                existing.restart()
                run = uow.suppliers.update_run(existing)
                queued = True
            else:
                run = existing
            uow.commit()
        if queued:
            try:
                self._queue.enqueue(run.id)
            except Exception as exc:
                raise SupplierDiscoveryQueueFailure(str(exc)) from exc
        return SupplierDiscoveryRequestResponse(
            tender_id=tender_id,
            run=_run_response(run, reused=reused),
            queued=queued,
            reused=reused,
        )


class DiscoverSuppliers:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        search_service: SupplierSearchService,
    ) -> None:
        self._uow_factory = uow_factory
        self._search_service = search_service

    def execute(self, run_id: UUID) -> UUID:
        with self._uow_factory() as uow:
            run = uow.suppliers.get_run(run_id, for_update=True)
            if run is None:
                raise SupplierDiscoveryNotFound("Supplier discovery run was not found.")
            if _STAGE_ORDER[run.current_stage] > _STAGE_ORDER[SupplierDiscoveryStage.SEARCH]:
                return run.id
            snapshot = uow.catalogs.get_snapshot(run.catalog_snapshot_id)
            if snapshot is None:
                raise InvalidCatalogState("Approved catalog snapshot was not found.")
            run.start()
            uow.suppliers.update_run(run)
            uow.audit_events.append(
                supplier_event(
                    run.id,
                    "SupplierDiscoveryStarted",
                    aggregate_type="supplier_discovery",
                    tender_id=str(run.tender_id),
                    catalog_snapshot_id=str(run.catalog_snapshot_id),
                    search_provider=run.search_provider,
                    search_provider_version=run.search_provider_version,
                )
            )
            uow.commit()
            products = tuple(snapshot.products)
            configuration = dict(run.search_configuration)

        started = time.monotonic()
        candidates: list[dict[str, Any]] = []
        provider_errors: list[str] = []
        for product in products:
            product_id = UUID(str(product["product_id"]))
            request = SupplierSearchRequest(
                tender_id=run.tender_id,
                product=SupplierSearchProduct(
                    product_id=product_id,
                    name=str(product.get("name") or ""),
                    description=product.get("description"),
                    category=product.get("category"),
                    specifications=dict(product.get("specifications") or {}),
                ),
                country=configuration.get("country"),
                max_results=int(configuration.get("max_results_per_product", 10)),
            )
            try:
                response = self._search_service.search(request)
            except SupplierSearchFailure as exc:
                provider_errors.append(f"product={product_id}: {exc}")
                continue
            provider_errors.extend(
                f"product={product_id}: {message}" for message in response.provider_errors
            )
            candidates.extend(
                _suggestion_payload(product_id, suggestion)
                for suggestion in response.suggestions
            )
        if provider_errors and not candidates:
            raise SupplierSearchFailure("; ".join(provider_errors[:10]))
        duration_ms = round((time.monotonic() - started) * 1000)

        with self._uow_factory() as uow:
            current = uow.suppliers.get_run(run_id, for_update=True)
            if current is None:
                raise SupplierDiscoveryNotFound("Supplier discovery run was not found.")
            current.save_search_results(
                candidates,
                duration_ms=duration_ms,
                provider_errors=provider_errors,
            )
            uow.suppliers.update_run(current)
            uow.audit_events.append(
                supplier_event(
                    current.id,
                    "SupplierDiscovered",
                    aggregate_type="supplier_discovery",
                    tender_id=str(current.tender_id),
                    suppliers_found=len(candidates),
                    provider_errors=len(provider_errors),
                    duration_ms=duration_ms,
                )
            )
            uow.commit()
        logger.info(
            "supplier_discovery_search_completed",
            extra={
                "supplier_discovery_run_id": str(run_id),
                "tender_id": str(run.tender_id),
                "suppliers_found": len(candidates),
                "provider_errors": len(provider_errors),
                "duration_ms": duration_ms,
            },
        )
        return run_id


class DeduplicateSuppliers:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        deduplication_service: SupplierDeduplicationService,
    ) -> None:
        self._uow_factory = uow_factory
        self._deduplication_service = deduplication_service

    def execute(self, run_id: UUID) -> UUID:
        with self._uow_factory() as uow:
            run = uow.suppliers.get_run(run_id, for_update=True)
            if run is None:
                raise SupplierDiscoveryNotFound("Supplier discovery run was not found.")
            if _STAGE_ORDER[run.current_stage] > _STAGE_ORDER[
                SupplierDiscoveryStage.DEDUPLICATION
            ]:
                return run.id
            suppliers = uow.suppliers.list_suppliers()
            contacts_by_supplier = {
                supplier.id: uow.suppliers.list_contacts(supplier.id)
                for supplier in suppliers
            }
            processed: list[dict[str, Any]] = []
            duplicates_detected = 0
            for raw in run.raw_candidates:
                suggestion = _suggestion_from_payload(raw)
                duplicate = self._deduplication_service.find_best(
                    suggestion,
                    suppliers,
                    contacts_by_supplier,
                )
                if duplicate and duplicate.exact_identity:
                    supplier = uow.suppliers.get_supplier(duplicate.supplier_id)
                    if supplier is None:
                        raise SupplierDiscoveryNotFound("Duplicate supplier was not found.")
                    duplicates_detected += 1
                    duplicate_type = "exact_reuse"
                else:
                    supplier = uow.suppliers.create_supplier(
                        Supplier(
                            legal_name=suggestion.legal_name,
                            trade_name=suggestion.trade_name,
                            website=suggestion.website,
                            category=suggestion.category,
                            country=suggestion.country,
                            city=suggestion.city,
                            description=suggestion.description,
                        )
                    )
                    suppliers.append(supplier)
                    contacts_by_supplier[supplier.id] = []
                    duplicate_type = "new_master"
                    if (
                        duplicate
                        and duplicate.score
                        >= self._deduplication_service.suggestion_threshold
                    ):
                        duplicates_detected += 1
                        existing_suggestion = uow.suppliers.find_merge_suggestion(
                            supplier.id, duplicate.supplier_id
                        )
                        if existing_suggestion is None:
                            uow.suppliers.create_merge_suggestion(
                                SupplierMergeSuggestion(
                                    source_supplier_id=supplier.id,
                                    target_supplier_id=duplicate.supplier_id,
                                    discovery_run_id=run.id,
                                    score=SupplierConfidence(duplicate.score),
                                    signals=duplicate.signals,
                                )
                            )
                        duplicate_type = "merge_suggestion"

                if suggestion.source_url and not uow.suppliers.source_exists(
                    supplier.id, suggestion.source_url
                ):
                    uow.suppliers.add_source(
                        SupplierSource(
                            supplier_id=supplier.id,
                            provider_name=run.search_provider,
                            source_type=suggestion.source_type,
                            source_url=suggestion.source_url,
                            source_title=suggestion.source_title,
                            excerpt=suggestion.source_excerpt,
                        )
                    )
                tender_supplier = uow.suppliers.find_tender_supplier(
                    run.tender_id, supplier.id
                )
                if tender_supplier is None:
                    tender_supplier = uow.suppliers.create_tender_supplier(
                        TenderSupplier(
                            tender_id=run.tender_id,
                            supplier_id=supplier.id,
                            discovery_run_id=run.id,
                        )
                    )
                processed.append(
                    {
                        **raw,
                        "supplier_id": str(supplier.id),
                        "tender_supplier_id": str(tender_supplier.id),
                        "duplicate_type": duplicate_type,
                        "duplicate_score": duplicate.score if duplicate else 0.0,
                        "duplicate_signals": list(duplicate.signals) if duplicate else [],
                    }
                )
            run.save_deduplicated(
                processed,
                duplicates_detected=duplicates_detected,
            )
            uow.suppliers.update_run(run)
            uow.audit_events.append(
                supplier_event(
                    run.id,
                    "SupplierDeduplicated",
                    aggregate_type="supplier_discovery",
                    tender_id=str(run.tender_id),
                    candidates=len(processed),
                    duplicates_detected=duplicates_detected,
                    deduplication_version=self._deduplication_service.version,
                )
            )
            uow.commit()
        return run_id


class DiscoverSupplierContacts:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, run_id: UUID) -> UUID:
        with self._uow_factory() as uow:
            run = uow.suppliers.get_run(run_id, for_update=True)
            if run is None:
                raise SupplierDiscoveryNotFound("Supplier discovery run was not found.")
            if _STAGE_ORDER[run.current_stage] > _STAGE_ORDER[SupplierDiscoveryStage.CONTACTS]:
                return run.id
            contacts_found = 0
            touched: set[UUID] = set()
            for raw in run.processed_candidates:
                suggestion = _suggestion_from_payload(raw)
                supplier_id = UUID(str(raw["supplier_id"]))
                tender_supplier_id = UUID(str(raw["tender_supplier_id"]))
                touched.add(tender_supplier_id)
                for item in suggestion.contacts:
                    contact = SupplierContact(
                        supplier_id=supplier_id,
                        contact_type=SupplierContactType(item.contact_type),
                        value=item.value,
                        confidence=SupplierConfidence(item.confidence),
                        source_url=item.source_url or suggestion.source_url,
                        contact_name=item.contact_name,
                        role=item.role,
                    )
                    if not uow.suppliers.contact_exists(supplier_id, contact.identity_key):
                        uow.suppliers.add_contact(contact)
                        contacts_found += 1
            for tender_supplier_id in touched:
                tender_supplier = uow.suppliers.get_tender_supplier(tender_supplier_id)
                if tender_supplier is None:
                    continue
                if tender_supplier.status is SupplierStatus.CANDIDATE:
                    tender_supplier.mark_contact_discovery_complete()
                    uow.suppliers.update_tender_supplier(tender_supplier)
                uow.audit_events.append(
                    supplier_event(
                        tender_supplier.id,
                        "SupplierContactsDiscovered",
                        tender_id=str(tender_supplier.tender_id),
                        supplier_id=str(tender_supplier.supplier_id),
                        contact_count=len(
                            uow.suppliers.list_contacts(tender_supplier.supplier_id)
                        ),
                    )
                )
            run.mark_contacts_complete(contacts_found)
            uow.suppliers.update_run(run)
            uow.commit()
        return run_id


class MatchSuppliers:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        matching_service: SupplierMatchingService,
    ) -> None:
        self._uow_factory = uow_factory
        self._matching_service = matching_service

    def execute(self, run_id: UUID) -> UUID:
        started = time.monotonic()
        with self._uow_factory() as uow:
            run = uow.suppliers.get_run(run_id, for_update=True)
            if run is None:
                raise SupplierDiscoveryNotFound("Supplier discovery run was not found.")
            if _STAGE_ORDER[run.current_stage] > _STAGE_ORDER[SupplierDiscoveryStage.MATCHING]:
                return run.id
            matches_completed = 0
            unique_pairs: set[tuple[UUID, UUID]] = set()
            for raw in run.processed_candidates:
                tender_supplier_id = UUID(str(raw["tender_supplier_id"]))
                product_id = UUID(str(raw["product_id"]))
                pair = (tender_supplier_id, product_id)
                if pair in unique_pairs:
                    continue
                unique_pairs.add(pair)
                tender_supplier = uow.suppliers.get_tender_supplier(tender_supplier_id)
                supplier = (
                    uow.suppliers.get_supplier(tender_supplier.supplier_id)
                    if tender_supplier
                    else None
                )
                product = uow.catalogs.get_product(product_id)
                if tender_supplier is None or supplier is None or product is None:
                    continue
                result = self._matching_service.calculate(
                    product.snapshot_payload(), supplier
                )
                existing = uow.suppliers.get_match(tender_supplier_id, product_id)
                if existing is None:
                    match = ProductSupplierMatch(
                        tender_supplier_id=tender_supplier_id,
                        product_id=product_id,
                        score=SupplierMatchScore(result.score),
                        components=result.components,
                        reasons=result.reasons,
                        algorithm_version=self._matching_service.version,
                    )
                    uow.suppliers.create_match(match)
                else:
                    match = ProductSupplierMatch(
                        id=existing.id,
                        tender_supplier_id=tender_supplier_id,
                        product_id=product_id,
                        score=SupplierMatchScore(result.score),
                        components=result.components,
                        reasons=result.reasons,
                        algorithm_version=self._matching_service.version,
                        created_at=existing.created_at,
                    )
                    uow.suppliers.update_match(match)
                matches_completed += 1
            duration_ms = round((time.monotonic() - started) * 1000)
            run.mark_matching_complete(duration_ms)
            uow.suppliers.update_run(run)
            uow.audit_events.append(
                supplier_event(
                    run.id,
                    "SupplierMatchingCompleted",
                    aggregate_type="supplier_discovery",
                    tender_id=str(run.tender_id),
                    matches_completed=matches_completed,
                    duration_ms=duration_ms,
                    algorithm_version=self._matching_service.version,
                )
            )
            uow.commit()
        return run_id


class StartSupplierReview:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, run_id: UUID) -> UUID:
        with self._uow_factory() as uow:
            run = uow.suppliers.get_run(run_id, for_update=True)
            if run is None:
                raise SupplierDiscoveryNotFound("Supplier discovery run was not found.")
            if run.status is SupplierDiscoveryRunStatus.COMPLETED:
                return run.id
            for tender_supplier in uow.suppliers.list_tender_suppliers(run.tender_id):
                if tender_supplier.discovery_run_id != run.id:
                    continue
                if tender_supplier.status is SupplierStatus.CANDIDATE:
                    tender_supplier.mark_contact_discovery_complete()
                if tender_supplier.status is SupplierStatus.CONTACTS_FOUND:
                    tender_supplier.start_review()
                    uow.suppliers.update_tender_supplier(tender_supplier)
            run.complete()
            uow.suppliers.update_run(run)
            uow.commit()
        logger.info(
            "supplier_discovery_completed",
            extra={
                "supplier_discovery_run_id": str(run_id),
                "tender_id": str(run.tender_id),
                "suppliers_found": run.suppliers_found,
                "duplicates_detected": run.duplicates_detected,
                "contacts_found": run.contacts_found,
                "search_duration_ms": run.search_duration_ms,
                "matching_duration_ms": run.matching_duration_ms,
            },
        )
        return run_id


class ProcessSupplierDiscoveryRun:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        search_service: SupplierSearchService,
        deduplication_service: SupplierDeduplicationService,
        matching_service: SupplierMatchingService,
    ) -> None:
        self._uow_factory = uow_factory
        self._search_service = search_service
        self._deduplication_service = deduplication_service
        self._matching_service = matching_service

    def execute(self, run_id: UUID) -> UUID:
        try:
            DiscoverSuppliers(self._uow_factory, self._search_service).execute(run_id)
            DeduplicateSuppliers(
                self._uow_factory, self._deduplication_service
            ).execute(run_id)
            DiscoverSupplierContacts(self._uow_factory).execute(run_id)
            MatchSuppliers(self._uow_factory, self._matching_service).execute(run_id)
            return StartSupplierReview(self._uow_factory).execute(run_id)
        except Exception as exc:
            with self._uow_factory() as uow:
                failed = uow.suppliers.get_run(run_id, for_update=True)
                if failed is not None and failed.status not in {
                    SupplierDiscoveryRunStatus.COMPLETED,
                    SupplierDiscoveryRunStatus.REUSED,
                }:
                    failed.fail(exc)
                    uow.suppliers.update_run(failed)
                    uow.commit()
            logger.exception(
                "supplier_discovery_failed",
                extra={"supplier_discovery_run_id": str(run_id)},
            )
            raise
