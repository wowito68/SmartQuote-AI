import hashlib
import json
import logging
import time
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.application.dtos.supplier_discovery_v2 import (
    ProductSupplierTraceResponse,
    ProductSuppliersResponse,
    SupplierCandidateTraceResponse,
    SupplierCandidatesResponse,
    SupplierDiscoveryRequestTraceResponse,
    SupplierDiscoveryRunTraceResponse,
)
from app.application.exceptions import TenderNotFound
from app.application.ports.contact_discovery_service import ContactDiscoveryService
from app.application.ports.supplier_discovery_queue import SupplierDiscoveryQueue
from app.application.ports.supplier_search_service import (
    SupplierContactSuggestion,
    SupplierSearchProduct,
    SupplierSearchRequest,
    SupplierSearchService,
    SupplierSuggestion,
)
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.application.services.supplier_deduplication import (
    SupplierDeduplicationService,
    SupplierDuplicateStatus,
)
from app.application.services.supplier_matching import SupplierMatchingService
from app.application.services.supplier_normalization import SupplierCandidateNormalizer
from app.application.services.supplier_query_builder import SupplierQueryBuilder
from app.domain.catalog.exceptions import InvalidCatalogState
from app.domain.catalog.value_objects import ProductStatus
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
    InvalidSupplierState,
    SupplierDiscoveryNotFound,
    SupplierDiscoveryQueueFailure,
    SupplierNotFound,
    SupplierSearchFailure,
)
from app.domain.suppliers.value_objects import (
    SupplierConfidence,
    SupplierContactType,
    SupplierDiscoveryRunStatus,
    SupplierDiscoveryStage,
    SupplierMatchScore,
    SupplierMatchStatus,
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


def _suggestion_from_payload(payload: dict[str, Any]) -> SupplierSuggestion:
    searched_at = payload.get("searched_at")
    if isinstance(searched_at, str):
        searched_at = datetime.fromisoformat(searched_at)
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
        query=payload.get("query"),
        searched_at=searched_at,
        search_provider=payload.get("search_provider"),
        initial_score=(
            float(payload["initial_score"])
            if payload.get("initial_score") is not None
            else None
        ),
    )


def _suggestion_payload(
    product_id: UUID,
    suggestion: SupplierSuggestion,
    *,
    query: str,
    search_provider: str,
    estimated_cost_usd: float,
) -> dict[str, Any]:
    searched_at = suggestion.searched_at or datetime.now(UTC)
    initial_score = suggestion.initial_score
    if initial_score is None:
        value = suggestion.metadata.get("directory_score")
        initial_score = float(value) if value is not None else None
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
        "metadata": dict(suggestion.metadata),
        "query": query,
        "searched_at": searched_at.isoformat(),
        "search_provider": suggestion.search_provider or search_provider,
        "initial_score": initial_score,
        "estimated_cost_usd": estimated_cost_usd,
    }


def _run_trace(run: SupplierDiscoveryRun, *, reused: bool) -> SupplierDiscoveryRunTraceResponse:
    configuration = dict(run.search_configuration)
    refresh_of = configuration.get("refresh_of_run_id")
    return SupplierDiscoveryRunTraceResponse(
        id=run.id,
        tender_id=run.tender_id,
        catalog_snapshot_id=run.catalog_snapshot_id,
        status=run.status,
        current_stage=run.current_stage,
        search_provider=run.search_provider,
        search_provider_version=run.search_provider_version,
        matching_algorithm_version=run.matching_algorithm_version,
        query_version=str(configuration.get("query_version") or "legacy"),
        search_identity_key=str(configuration.get("search_identity_key") or run.idempotency_key),
        correlation_id=str(configuration.get("correlation_id") or ""),
        refresh_sequence=int(configuration.get("refresh_sequence") or 1),
        refresh_of_run_id=UUID(str(refresh_of)) if refresh_of else None,
        estimated_cost_usd=float(configuration.get("estimated_cost_usd") or 0.0),
        reused=reused,
        created_at=run.created_at,
    )


class RequestSupplierDiscoveryV2:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        queue: SupplierDiscoveryQueue,
        search_service: SupplierSearchService,
        matching_service: SupplierMatchingService,
        deduplication_service: SupplierDeduplicationService,
        query_builder: SupplierQueryBuilder,
        contact_service: ContactDiscoveryService,
        *,
        search_configuration: dict[str, Any],
    ) -> None:
        self._uow_factory = uow_factory
        self._queue = queue
        self._search_service = search_service
        self._matching_service = matching_service
        self._deduplication_service = deduplication_service
        self._query_builder = query_builder
        self._contact_service = contact_service
        self._search_configuration = search_configuration

    def execute(
        self,
        tender_id: UUID,
        requested_by_user_id: UUID,
        *,
        refresh: bool = False,
        correlation_id: str,
    ) -> SupplierDiscoveryRequestTraceResponse:
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
            identity = _canonical_hash(
                {
                    "tender_id": str(tender_id),
                    "approved_catalog_version": snapshot.version,
                    "catalog_snapshot_id": str(snapshot.id),
                    "search_provider": self._search_service.provider_name,
                    "search_provider_version": self._search_service.provider_version,
                    "query_version": self._query_builder.version,
                    "deduplication_version": self._deduplication_service.version,
                    "matching_version": self._matching_service.version,
                    "contact_provider": self._contact_service.provider_name,
                    "contact_provider_version": self._contact_service.provider_version,
                    "criteria": self._search_configuration,
                }
            )
            matching_runs = [
                candidate
                for candidate in uow.suppliers.list_runs(tender_id)
                if candidate.search_configuration.get("search_identity_key") == identity
            ]
            matching_runs.sort(key=lambda candidate: candidate.created_at)
            latest = matching_runs[-1] if matching_runs else None
            if latest and not refresh and latest.status in {
                SupplierDiscoveryRunStatus.COMPLETED,
                SupplierDiscoveryRunStatus.REUSED,
            }:
                run = latest
                reused = True
            elif latest and not refresh and latest.status in {
                SupplierDiscoveryRunStatus.QUEUED,
                SupplierDiscoveryRunStatus.RUNNING,
            }:
                run = latest
            else:
                sequence = len(matching_runs) + 1
                execution_key = _canonical_hash(
                    {"search_identity_key": identity, "refresh_sequence": sequence}
                )
                configuration = {
                    **self._search_configuration,
                    "query_version": self._query_builder.version,
                    "search_identity_key": identity,
                    "correlation_id": correlation_id[:128],
                    "refresh_sequence": sequence,
                    "refresh_of_run_id": str(latest.id) if latest else None,
                    "estimated_cost_usd": 0.0,
                }
                run = uow.suppliers.create_run(
                    SupplierDiscoveryRun(
                        tender_id=tender_id,
                        catalog_snapshot_id=snapshot.id,
                        requested_by_user_id=requested_by_user_id,
                        idempotency_key=execution_key,
                        search_provider=self._search_service.provider_name,
                        search_provider_version=self._search_service.provider_version,
                        search_configuration=configuration,
                        matching_algorithm_version=self._matching_service.version,
                    )
                )
                uow.audit_events.append(
                    supplier_event(
                        run.id,
                        "SupplierDiscoveryRequested",
                        aggregate_type="supplier_discovery",
                        tender_id=str(tender_id),
                        search_identity_key=identity,
                        refresh=refresh,
                        refresh_sequence=sequence,
                        correlation_id=correlation_id[:128],
                    )
                )
                queued = True
            uow.commit()
        if queued:
            try:
                self._queue.enqueue(run.id)
            except Exception as exc:
                raise SupplierDiscoveryQueueFailure(str(exc)) from exc
        return SupplierDiscoveryRequestTraceResponse(
            tender_id=tender_id,
            run=_run_trace(run, reused=reused),
            queued=queued,
            reused=reused,
        )


class DiscoverSuppliersV2:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        search_service: SupplierSearchService,
        query_builder: SupplierQueryBuilder,
    ) -> None:
        self._uow_factory = uow_factory
        self._search_service = search_service
        self._query_builder = query_builder

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
                    correlation_id=run.search_configuration.get("correlation_id"),
                    search_provider=run.search_provider,
                    query_version=self._query_builder.version,
                )
            )
            uow.commit()
            products = tuple(snapshot.products)
            configuration = dict(run.search_configuration)

        started = time.monotonic()
        candidates: list[dict[str, Any]] = []
        provider_errors: list[str] = []
        estimated_cost_usd = 0.0
        for product in products:
            product_id = UUID(str(product["product_id"]))
            search_product = SupplierSearchProduct(
                product_id=product_id,
                name=str(product.get("name") or ""),
                description=product.get("description"),
                category=product.get("category"),
                specifications=dict(product.get("specifications") or {}),
            )
            query = self._query_builder.build(
                search_product,
                country=configuration.get("country"),
                city=configuration.get("city"),
                keywords=tuple(configuration.get("keywords") or ()),
            )
            request = SupplierSearchRequest(
                tender_id=run.tender_id,
                product=search_product,
                country=configuration.get("country"),
                city=configuration.get("city"),
                max_results=int(configuration.get("max_results_per_product", 10)),
                query=query.text,
                query_version=query.version,
            )
            try:
                response = self._search_service.search(request)
            except SupplierSearchFailure as exc:
                provider_errors.append(f"product={product_id}: {exc}")
                continue
            estimated_cost_usd += response.estimated_cost_usd
            provider_errors.extend(
                f"product={product_id}: {message}" for message in response.provider_errors
            )
            candidates.extend(
                _suggestion_payload(
                    product_id,
                    suggestion,
                    query=query.text,
                    search_provider=self._search_service.provider_name,
                    estimated_cost_usd=response.estimated_cost_usd,
                )
                for suggestion in response.suggestions
            )
        if provider_errors and not candidates:
            raise SupplierSearchFailure("; ".join(provider_errors[:10]))
        duration_ms = round((time.monotonic() - started) * 1000)

        with self._uow_factory() as uow:
            current = uow.suppliers.get_run(run_id, for_update=True)
            if current is None:
                raise SupplierDiscoveryNotFound("Supplier discovery run was not found.")
            current.search_configuration["estimated_cost_usd"] = round(estimated_cost_usd, 6)
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
                    estimated_cost_usd=round(estimated_cost_usd, 6),
                    duration_ms=duration_ms,
                    correlation_id=current.search_configuration.get("correlation_id"),
                )
            )
            uow.commit()
        return run_id


class NormalizeSupplierCandidates:
    def __init__(self, uow_factory: UnitOfWorkFactory, normalizer: SupplierCandidateNormalizer) -> None:
        self._uow_factory = uow_factory
        self._normalizer = normalizer

    def execute(self, run_id: UUID) -> UUID:
        with self._uow_factory() as uow:
            run = uow.suppliers.get_run(run_id, for_update=True)
            if run is None:
                raise SupplierDiscoveryNotFound("Supplier discovery run was not found.")
            if run.current_stage is not SupplierDiscoveryStage.DEDUPLICATION:
                return run.id
            normalized: list[dict[str, Any]] = []
            for raw in run.raw_candidates:
                item = dict(raw)
                item["normalization"] = asdict(
                    self._normalizer.normalize(_suggestion_from_payload(raw))
                )
                normalized.append(item)
            run.raw_candidates = normalized
            uow.suppliers.update_run(run)
            uow.audit_events.append(
                supplier_event(
                    run.id,
                    "SupplierCandidatesNormalized",
                    aggregate_type="supplier_discovery",
                    tender_id=str(run.tender_id),
                    normalizer_version=self._normalizer.version,
                    candidates=len(normalized),
                )
            )
            uow.commit()
        return run_id


class DeduplicateSuppliersV2:
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
                supplier.id: uow.suppliers.list_contacts(supplier.id) for supplier in suppliers
            }
            processed: list[dict[str, Any]] = []
            duplicates_detected = 0
            for raw in run.raw_candidates:
                suggestion = _suggestion_from_payload(raw)
                duplicate = self._deduplication_service.find_best(
                    suggestion, suppliers, contacts_by_supplier
                )
                duplicate_status = (
                    duplicate.status if duplicate else SupplierDuplicateStatus.UNIQUE
                )
                if duplicate and duplicate.status is SupplierDuplicateStatus.DUPLICATE:
                    supplier = uow.suppliers.get_supplier(duplicate.supplier_id)
                    if supplier is None:
                        raise SupplierDiscoveryNotFound("Duplicate supplier was not found.")
                    duplicates_detected += 1
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
                    if (
                        duplicate
                        and duplicate.status is SupplierDuplicateStatus.POSSIBLE_DUPLICATE
                    ):
                        duplicates_detected += 1
                        if uow.suppliers.find_merge_suggestion(
                            supplier.id, duplicate.supplier_id
                        ) is None:
                            uow.suppliers.create_merge_suggestion(
                                SupplierMergeSuggestion(
                                    source_supplier_id=supplier.id,
                                    target_supplier_id=duplicate.supplier_id,
                                    discovery_run_id=run.id,
                                    score=SupplierConfidence(duplicate.score),
                                    signals=duplicate.signals,
                                )
                            )

                product_id = UUID(str(raw["product_id"]))
                existing_source = any(
                    source.discovery_run_id == run.id
                    and source.product_id == product_id
                    and source.source_url == suggestion.source_url
                    and source.query == str(raw.get("query") or "")
                    for source in uow.suppliers.list_sources(supplier.id)
                )
                if suggestion.source_url and not existing_source:
                    uow.suppliers.add_source(
                        SupplierSource(
                            supplier_id=supplier.id,
                            provider_name=str(raw.get("search_provider") or run.search_provider),
                            source_type=suggestion.source_type,
                            source_url=suggestion.source_url,
                            source_title=suggestion.source_title,
                            excerpt=suggestion.source_excerpt,
                            discovery_run_id=run.id,
                            product_id=product_id,
                            query=str(raw.get("query") or ""),
                            source_name=suggestion.source_title or run.search_provider,
                            metadata={
                                **dict(suggestion.metadata),
                                "normalization": raw.get("normalization") or {},
                                "initial_score": raw.get("initial_score"),
                                "estimated_cost_usd": raw.get("estimated_cost_usd", 0.0),
                            },
                            discovered_at=suggestion.searched_at or datetime.now(UTC),
                        )
                    )
                tender_supplier = uow.suppliers.find_tender_supplier(run.tender_id, supplier.id)
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
                        "duplicate_status": duplicate_status.value,
                        "duplicate_score": duplicate.score if duplicate else 0.0,
                        "duplicate_signals": list(duplicate.signals) if duplicate else [],
                    }
                )
            run.save_deduplicated(processed, duplicates_detected=duplicates_detected)
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


class DiscoverSupplierContactsV2:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        contact_service: ContactDiscoveryService,
    ) -> None:
        self._uow_factory = uow_factory
        self._contact_service = contact_service

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
                for item in self._contact_service.discover(suggestion):
                    contact = SupplierContact(
                        supplier_id=supplier_id,
                        contact_type=SupplierContactType(item.contact_type),
                        value=item.value,
                        confidence=SupplierConfidence(item.confidence),
                        source_url=item.source_url,
                        contact_name=item.contact_name,
                        role=item.role,
                    )
                    if not uow.suppliers.contact_exists(supplier_id, contact.identity_key):
                        uow.suppliers.add_contact(contact)
                        contacts_found += 1
            for tender_supplier_id in touched:
                tender_supplier = uow.suppliers.get_tender_supplier(tender_supplier_id)
                if tender_supplier and tender_supplier.status is SupplierStatus.CANDIDATE:
                    tender_supplier.mark_contact_discovery_complete()
                    uow.suppliers.update_tender_supplier(tender_supplier)
            run.mark_contacts_complete(contacts_found)
            uow.suppliers.update_run(run)
            uow.audit_events.append(
                supplier_event(
                    run.id,
                    "SupplierContactsDiscovered",
                    aggregate_type="supplier_discovery",
                    tender_id=str(run.tender_id),
                    contacts_found=contacts_found,
                    contact_provider=self._contact_service.provider_name,
                    contact_provider_version=self._contact_service.provider_version,
                )
            )
            uow.commit()
        return run_id


class MatchSuppliersV2:
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
            completed = 0
            seen: set[tuple[UUID, UUID]] = set()
            for raw in run.processed_candidates:
                tender_supplier_id = UUID(str(raw["tender_supplier_id"]))
                product_id = UUID(str(raw["product_id"]))
                pair = (tender_supplier_id, product_id)
                if pair in seen:
                    continue
                seen.add(pair)
                tender_supplier = uow.suppliers.get_tender_supplier(tender_supplier_id)
                supplier = (
                    uow.suppliers.get_supplier(tender_supplier.supplier_id)
                    if tender_supplier
                    else None
                )
                product = uow.catalogs.get_product(product_id)
                if tender_supplier is None or supplier is None or product is None:
                    continue
                result = self._matching_service.calculate(product.snapshot_payload(), supplier)
                existing = uow.suppliers.get_match(tender_supplier_id, product_id)
                match = ProductSupplierMatch(
                    id=existing.id if existing else UUID(int=0),
                    tender_supplier_id=tender_supplier_id,
                    product_id=product_id,
                    score=SupplierMatchScore(result.score),
                    components=result.components,
                    reasons=result.reasons,
                    algorithm_version=self._matching_service.version,
                    match_status=(
                        existing.match_status if existing else SupplierMatchStatus.CANDIDATE
                    ),
                    source_url=str(raw.get("source_url") or "") or None,
                    reason="; ".join(result.reasons),
                    created_at=existing.created_at if existing else datetime.now(UTC),
                )
                if existing is None:
                    match = ProductSupplierMatch(
                        tender_supplier_id=match.tender_supplier_id,
                        product_id=match.product_id,
                        score=match.score,
                        components=match.components,
                        reasons=match.reasons,
                        algorithm_version=match.algorithm_version,
                        match_status=match.match_status,
                        source_url=match.source_url,
                        reason=match.reason,
                        created_at=match.created_at,
                    )
                    uow.suppliers.create_match(match)
                else:
                    uow.suppliers.update_match(match)
                completed += 1
            duration_ms = round((time.monotonic() - started) * 1000)
            run.mark_matching_complete(duration_ms)
            uow.suppliers.update_run(run)
            uow.audit_events.append(
                supplier_event(
                    run.id,
                    "SupplierMatchingCompleted",
                    aggregate_type="supplier_discovery",
                    tender_id=str(run.tender_id),
                    matches_completed=completed,
                    duration_ms=duration_ms,
                    algorithm_version=self._matching_service.version,
                )
            )
            uow.commit()
        return run_id


class CompleteSupplierDiscoveryV2:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, run_id: UUID) -> UUID:
        with self._uow_factory() as uow:
            run = uow.suppliers.get_run(run_id, for_update=True)
            if run is None:
                raise SupplierDiscoveryNotFound("Supplier discovery run was not found.")
            if run.status is SupplierDiscoveryRunStatus.COMPLETED:
                return run.id
            for raw in run.processed_candidates:
                tender_supplier = uow.suppliers.get_tender_supplier(
                    UUID(str(raw["tender_supplier_id"]))
                )
                if tender_supplier is None:
                    continue
                if tender_supplier.status is SupplierStatus.CANDIDATE:
                    tender_supplier.mark_contact_discovery_complete()
                if tender_supplier.status is SupplierStatus.CONTACTS_FOUND:
                    tender_supplier.start_review()
                    uow.suppliers.update_tender_supplier(tender_supplier)
            run.complete()
            uow.suppliers.update_run(run)
            uow.audit_events.append(
                supplier_event(
                    run.id,
                    "SupplierDiscoveryCompleted",
                    aggregate_type="supplier_discovery",
                    tender_id=str(run.tender_id),
                    correlation_id=run.search_configuration.get("correlation_id"),
                )
            )
            uow.commit()
        return run_id


class ProcessSupplierDiscoveryRunV2:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        search_service: SupplierSearchService,
        query_builder: SupplierQueryBuilder,
        normalizer: SupplierCandidateNormalizer,
        deduplication_service: SupplierDeduplicationService,
        contact_service: ContactDiscoveryService,
        matching_service: SupplierMatchingService,
    ) -> None:
        self._uow_factory = uow_factory
        self._search_service = search_service
        self._query_builder = query_builder
        self._normalizer = normalizer
        self._deduplication_service = deduplication_service
        self._contact_service = contact_service
        self._matching_service = matching_service

    def execute(self, run_id: UUID) -> UUID:
        correlation_id = ""
        try:
            with self._uow_factory() as uow:
                run = uow.suppliers.get_run(run_id)
                if run is not None:
                    correlation_id = str(run.search_configuration.get("correlation_id") or "")
            DiscoverSuppliersV2(
                self._uow_factory, self._search_service, self._query_builder
            ).execute(run_id)
            NormalizeSupplierCandidates(self._uow_factory, self._normalizer).execute(run_id)
            DeduplicateSuppliersV2(
                self._uow_factory, self._deduplication_service
            ).execute(run_id)
            DiscoverSupplierContactsV2(
                self._uow_factory, self._contact_service
            ).execute(run_id)
            MatchSuppliersV2(self._uow_factory, self._matching_service).execute(run_id)
            return CompleteSupplierDiscoveryV2(self._uow_factory).execute(run_id)
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
                extra={
                    "supplier_discovery_run_id": str(run_id),
                    "correlation_id": correlation_id,
                },
            )
            raise


class ListSupplierCandidates:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, tender_id: UUID) -> SupplierCandidatesResponse:
        candidates: list[SupplierCandidateTraceResponse] = []
        with self._uow_factory() as uow:
            if uow.tenders.get_by_id(tender_id) is None:
                raise TenderNotFound("Tender was not found.")
            for run in uow.suppliers.list_runs(tender_id):
                for raw in run.processed_candidates:
                    tender_supplier_id = UUID(str(raw["tender_supplier_id"]))
                    product_id = UUID(str(raw["product_id"]))
                    supplier_id = UUID(str(raw["supplier_id"]))
                    tender_supplier = uow.suppliers.get_tender_supplier(tender_supplier_id)
                    match = uow.suppliers.get_match(tender_supplier_id, product_id)
                    if tender_supplier is None:
                        continue
                    searched_at = raw.get("searched_at")
                    candidates.append(
                        SupplierCandidateTraceResponse(
                            run_id=run.id,
                            product_id=product_id,
                            supplier_id=supplier_id,
                            tender_supplier_id=tender_supplier_id,
                            status=tender_supplier.status,
                            legal_name=raw.get("legal_name"),
                            trade_name=raw.get("trade_name"),
                            website=raw.get("website"),
                            normalized=dict(raw.get("normalization") or {}),
                            source_url=str(raw.get("source_url") or ""),
                            source_title=raw.get("source_title"),
                            source_type=str(raw.get("source_type") or "search_result"),
                            query=str(raw.get("query") or ""),
                            search_provider=str(raw.get("search_provider") or run.search_provider),
                            searched_at=(
                                datetime.fromisoformat(searched_at)
                                if isinstance(searched_at, str)
                                else searched_at
                            ),
                            initial_score=(
                                float(raw["initial_score"])
                                if raw.get("initial_score") is not None
                                else None
                            ),
                            duplicate_status=str(raw.get("duplicate_status") or "unique"),
                            duplicate_score=float(raw.get("duplicate_score") or 0.0),
                            duplicate_signals=tuple(raw.get("duplicate_signals") or ()),
                            match_score=match.score.value if match else None,
                            match_status=match.match_status if match else None,
                            match_reasons=match.reasons if match else (),
                        )
                    )
        return SupplierCandidatesResponse(tender_id=tender_id, candidates=tuple(candidates))


class ListProductSuppliers:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, product_id: UUID) -> ProductSuppliersResponse:
        with self._uow_factory() as uow:
            product = uow.catalogs.get_product(product_id)
            if product is None:
                raise InvalidCatalogState("Catalog product was not found.")
            results: list[ProductSupplierTraceResponse] = []
            for item in uow.suppliers.list_tender_suppliers(product.tender_id):
                match = uow.suppliers.get_match(item.id, product_id)
                if match is None:
                    continue
                supplier = uow.suppliers.get_supplier(item.supplier_id)
                if supplier is None:
                    continue
                results.append(
                    ProductSupplierTraceResponse(
                        product_id=product_id,
                        tender_supplier_id=item.id,
                        supplier_id=supplier.id,
                        status=item.status,
                        legal_name=supplier.legal_name,
                        trade_name=supplier.trade_name,
                        website=supplier.website,
                        match_score=match.score.value,
                        match_status=match.match_status,
                        source_url=match.source_url,
                        reason=match.reason or match.reasons[0],
                        reasons=match.reasons,
                    )
                )
        results.sort(key=lambda item: item.match_score, reverse=True)
        return ProductSuppliersResponse(product_id=product_id, suppliers=tuple(results))


class MatchSupplierToProduct:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        matching_service: SupplierMatchingService,
    ) -> None:
        self._uow_factory = uow_factory
        self._matching_service = matching_service

    def execute(
        self,
        product_id: UUID,
        tender_supplier_id: UUID,
        requested_by_user_id: UUID,
    ) -> ProductSupplierTraceResponse:
        with self._uow_factory() as uow:
            if not uow.users.exists(requested_by_user_id):
                raise InvalidSupplierState("Supplier match reviewer was not found.")
            product = uow.catalogs.get_product(product_id)
            if product is None or product.status is not ProductStatus.APPROVED:
                raise InvalidCatalogState("Product must be approved before confirming a supplier match.")
            item = uow.suppliers.get_tender_supplier(tender_supplier_id)
            if item is None:
                raise SupplierNotFound("Tender supplier was not found.")
            if item.status is not SupplierStatus.APPROVED:
                raise InvalidSupplierState(
                    "Supplier must be approved before confirming a product association."
                )
            supplier = uow.suppliers.get_supplier(item.supplier_id)
            if supplier is None or supplier.merged_into_supplier_id is not None:
                raise SupplierNotFound("Supplier master was not found.")
            result = self._matching_service.calculate(product.snapshot_payload(), supplier)
            existing = uow.suppliers.get_match(item.id, product_id)
            sources = uow.suppliers.list_sources(supplier.id)
            source_url = next(
                (source.source_url for source in reversed(sources) if source.product_id == product_id),
                sources[-1].source_url if sources else None,
            )
            match = ProductSupplierMatch(
                id=existing.id if existing else ProductSupplierMatch(
                    tender_supplier_id=item.id,
                    product_id=product_id,
                    score=SupplierMatchScore(result.score),
                    components=result.components,
                    reasons=result.reasons,
                    algorithm_version=self._matching_service.version,
                ).id,
                tender_supplier_id=item.id,
                product_id=product_id,
                score=SupplierMatchScore(result.score),
                components=result.components,
                reasons=result.reasons,
                algorithm_version=self._matching_service.version,
                match_status=SupplierMatchStatus.CONFIRMED,
                source_url=source_url,
                reason="; ".join(result.reasons),
                created_at=existing.created_at if existing else datetime.now(UTC),
            )
            if existing is None:
                uow.suppliers.create_match(match)
            else:
                uow.suppliers.update_match(match)
            uow.audit_events.append(
                supplier_event(
                    match.id,
                    "ProductSupplierMatchConfirmed",
                    product_id=str(product_id),
                    tender_supplier_id=str(item.id),
                    supplier_id=str(supplier.id),
                    requested_by_user_id=str(requested_by_user_id),
                    score=match.score.value,
                    reason=match.reason,
                )
            )
            uow.commit()
            return ProductSupplierTraceResponse(
                product_id=product_id,
                tender_supplier_id=item.id,
                supplier_id=supplier.id,
                status=item.status,
                legal_name=supplier.legal_name,
                trade_name=supplier.trade_name,
                website=supplier.website,
                match_score=match.score.value,
                match_status=match.match_status,
                source_url=match.source_url,
                reason=match.reason or match.reasons[0],
                reasons=match.reasons,
            )
