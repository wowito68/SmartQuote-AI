import hashlib
import json
import logging
from decimal import Decimal
from uuid import UUID

from app.application.dtos.catalog import (
    CatalogExtractionRequestResponse,
    CatalogExtractionRunResponse,
    CatalogMetricsResponse,
    CatalogProductResponse,
    CatalogSnapshotResponse,
    EvidenceReferenceResponse,
    TenderCatalogResponse,
)
from app.application.exceptions import TenderNotFound
from app.application.ports.ai_extraction_queue import AIExtractionQueue
from app.application.ports.ai_extraction_service import AIExtractionRequest, AIExtractionService
from app.application.ports.prompt_registry import PromptRegistry
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.application.services.ai_response_validation import validate_ai_payload
from app.application.services.catalog_normalizer import CatalogNormalizer
from app.domain.catalog.entities import (
    AIExtractionRun,
    CatalogProduct,
    CatalogSnapshot,
    EvidenceReference,
    ExtractedEvidence,
)
from app.domain.catalog.events import catalog_event
from app.domain.catalog.exceptions import (
    AIExtractionFailure,
    AIExtractionNotFound,
    AIResponseValidationError,
    CatalogProductNotFound,
    InvalidCatalogState,
)
from app.domain.catalog.value_objects import (
    AIExtractionRunStatus,
    ConfidenceScore,
    ProductStatus,
)
from app.domain.documents.exceptions import DocumentNotFound
from app.domain.documents.value_objects import DocumentStatus

logger = logging.getLogger(__name__)


def _schema_hash(schema: dict) -> str:
    return hashlib.sha256(
        json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _idempotency_key(
    *, file_hash: str, prompt_version: str, model: str, schema_hash: str
) -> str:
    value = "|".join((file_hash, prompt_version, model, schema_hash))
    return hashlib.sha256(value.encode()).hexdigest()


def _product_payload(product: CatalogProduct) -> dict:
    payload = product.snapshot_payload()
    payload.update(
        {
            "status": product.status.value,
            "manual_edit_count": product.manual_edit_count,
            "rejection_reason": product.rejection_reason,
        }
    )
    return payload


def _product_response(uow, product: CatalogProduct) -> CatalogProductResponse:
    evidence_items = []
    for evidence, reference in uow.catalogs.list_evidence(product.id):
        evidence_items.append(
            EvidenceReferenceResponse(
                document_id=evidence.document_id,
                page_number=evidence.page_number,
                text_fragment=evidence.text_fragment,
                confidence=evidence.confidence.value,
                x0=reference.x0,
                y0=reference.y0,
                x1=reference.x1,
                y1=reference.y1,
                model=evidence.model,
                prompt_version=evidence.prompt_version,
            )
        )
    return CatalogProductResponse(
        id=product.id,
        tender_id=product.tender_id,
        source_document_id=product.source_document_id,
        ai_extraction_run_id=product.ai_extraction_run_id,
        item_number=product.item_number,
        name=product.name,
        description=product.description,
        quantity=product.quantity.value if product.quantity else None,
        unit=product.unit,
        category=product.category,
        specifications=product.specifications,
        observations=product.observations,
        confidence=product.confidence.value,
        status=product.status,
        duplicate_of_product_id=product.duplicate_of_product_id,
        manual_edit_count=product.manual_edit_count,
        reviewed_by_user_id=product.reviewed_by_user_id,
        reviewed_at=product.reviewed_at,
        rejection_reason=product.rejection_reason,
        original_payload=product.original_payload,
        evidence=tuple(evidence_items),
    )


class RequestTenderCatalogExtraction:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        queue: AIExtractionQueue,
        prompt_registry: PromptRegistry,
        *,
        prompt_version: str,
        model: str,
        temperature: float,
    ) -> None:
        self._uow_factory = uow_factory
        self._queue = queue
        self._prompt_registry = prompt_registry
        self._prompt_version = prompt_version
        self._model = model
        self._temperature = temperature

    def execute(self, tender_id: UUID) -> CatalogExtractionRequestResponse:
        prompt = self._prompt_registry.get("catalog_extraction", self._prompt_version)
        schema_hash = _schema_hash(prompt.output_schema)
        queued_ids: list[UUID] = []
        responses: list[CatalogExtractionRunResponse] = []
        with self._uow_factory() as uow:
            tender = uow.tenders.get_by_id(tender_id)
            if tender is None:
                raise TenderNotFound("Tender was not found.")
            documents = [
                document
                for document in uow.documents.list_by_tender(tender_id)
                if document.status is DocumentStatus.READY_FOR_AI
            ]
            if not documents:
                raise InvalidCatalogState(
                    "Tender has no documents ready for AI catalog extraction."
                )
            for document in documents:
                key = _idempotency_key(
                    file_hash=document.file_hash.value,
                    prompt_version=prompt.version,
                    model=self._model,
                    schema_hash=schema_hash,
                )
                existing = uow.catalogs.get_run_by_idempotency(document.id, key)
                reused = False
                if existing is None:
                    run = uow.catalogs.create_run(
                        AIExtractionRun(
                            tender_id=tender_id,
                            document_id=document.id,
                            idempotency_key=key,
                            prompt_version=prompt.version,
                            model=self._model,
                            temperature=self._temperature,
                            schema_version=prompt.schema_version,
                            schema_hash=schema_hash,
                        )
                    )
                    queued_ids.append(run.id)
                elif existing.status in {
                    AIExtractionRunStatus.COMPLETED,
                    AIExtractionRunStatus.REUSED,
                }:
                    run = existing
                    reused = True
                elif existing.status is AIExtractionRunStatus.FAILED:
                    existing.restart()
                    run = uow.catalogs.update_run(existing)
                    queued_ids.append(run.id)
                else:
                    run = existing
                responses.append(
                    CatalogExtractionRunResponse(
                        id=run.id,
                        document_id=run.document_id,
                        status=run.status,
                        prompt_version=run.prompt_version,
                        model=run.model,
                        reused=reused,
                    )
                )
            uow.commit()
        for run_id in queued_ids:
            self._queue.enqueue(run_id)
        return CatalogExtractionRequestResponse(
            tender_id=tender_id,
            runs=tuple(responses),
            queued=len(queued_ids),
            reused=sum(item.reused for item in responses),
        )


class ProcessAIExtractionRun:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        ai_service: AIExtractionService,
        prompt_registry: PromptRegistry,
        normalizer: CatalogNormalizer,
    ) -> None:
        self._uow_factory = uow_factory
        self._ai_service = ai_service
        self._prompt_registry = prompt_registry
        self._normalizer = normalizer

    def execute(self, run_id: UUID) -> UUID:
        with self._uow_factory() as uow:
            run = uow.catalogs.get_run(run_id, for_update=True)
            if run is None:
                raise AIExtractionNotFound("AI extraction run was not found.")
            if run.status in {AIExtractionRunStatus.COMPLETED, AIExtractionRunStatus.REUSED}:
                return run.id
            document = uow.documents.get_by_id(run.document_id)
            if document is None:
                raise DocumentNotFound("Document was not found.")
            if document.status is not DocumentStatus.READY_FOR_AI:
                raise InvalidCatalogState("Document is not ready for AI extraction.")
            pages = uow.extractions.list_pages(document.id)
            if not pages:
                raise InvalidCatalogState("Document has no extracted pages.")
            run.start()
            uow.catalogs.update_run(run)
            uow.audit_events.append(
                catalog_event(
                    run.id,
                    "AIExtractionStarted",
                    aggregate_type="ai_extraction",
                    tender_id=str(run.tender_id),
                    document_id=str(run.document_id),
                    prompt_version=run.prompt_version,
                    model=run.model,
                )
            )
            uow.commit()
            request_pages = tuple(
                {"page_number": page.page_number, "text": page.text} for page in pages
            )

        prompt = self._prompt_registry.get("catalog_extraction", run.prompt_version)
        try:
            result = self._ai_service.extract(
                AIExtractionRequest(
                    prompt=prompt,
                    model=run.model,
                    temperature=run.temperature,
                    document_id=str(run.document_id),
                    pages=request_pages,
                )
            )
            validated = validate_ai_payload(result.payload)
            page_text = {page["page_number"]: page["text"] for page in request_pages}
            with self._uow_factory() as uow:
                current = uow.catalogs.get_run(run.id, for_update=True)
                if current is None:
                    raise AIExtractionNotFound("AI extraction run disappeared.")
                if uow.catalogs.list_products_by_run(current.id):
                    return current.id
                existing_products = uow.catalogs.list_products(current.tender_id)
                fingerprints: dict[str, UUID] = {}
                for existing in existing_products:
                    normalized = self._normalizer.normalize(
                        name=existing.name,
                        description=existing.description,
                        quantity=existing.quantity.value if existing.quantity else None,
                        unit=existing.unit,
                        category=existing.category,
                        specifications=existing.specifications,
                        observations=existing.observations,
                    )
                    fingerprints.setdefault(normalized.fingerprint, existing.id)

                created_products: list[CatalogProduct] = []
                for item in validated.products:
                    raw = item.model_dump(mode="json")
                    specifications = {
                        specification.name: specification.value
                        for specification in item.technical_specifications
                    }
                    product = uow.catalogs.create_product(
                        CatalogProduct(
                            tender_id=current.tender_id,
                            ai_extraction_run_id=current.id,
                            source_document_id=current.document_id,
                            original_payload=raw,
                            item_number=item.item_number,
                            name=item.name,
                            description=item.description,
                            quantity=None,
                            unit=item.unit,
                            category=item.suggested_category,
                            specifications=specifications,
                            observations=item.observations,
                            confidence=ConfidenceScore(item.confidence),
                        )
                    )
                    uow.audit_events.append(
                        catalog_event(
                            product.id,
                            "ProductCandidateCreated",
                            aggregate_type="catalog_product",
                            tender_id=str(product.tender_id),
                            document_id=str(product.source_document_id),
                            ai_extraction_run_id=str(current.id),
                            confidence=product.confidence.value,
                        )
                    )
                    normalized = self._normalizer.normalize(
                        name=item.name,
                        description=item.description,
                        quantity=item.quantity,
                        unit=item.unit,
                        category=item.suggested_category,
                        specifications=specifications,
                        observations=item.observations,
                    )
                    product.apply_normalization(
                        name=normalized.name,
                        description=normalized.description,
                        quantity=normalized.quantity,
                        unit=normalized.unit,
                        category=normalized.category,
                        specifications=normalized.specifications,
                        observations=normalized.observations,
                        duplicate_of_product_id=fingerprints.get(normalized.fingerprint),
                    )
                    product.start_review()
                    product = uow.catalogs.update_product(product)
                    fingerprints.setdefault(normalized.fingerprint, product.id)
                    created_products.append(product)

                    for evidence_item in item.evidence:
                        source_text = page_text.get(evidence_item.page)
                        if source_text is None:
                            raise AIResponseValidationError(
                                f"Evidence references missing page {evidence_item.page}."
                            )
                        fragment = " ".join(evidence_item.fragment.split())
                        compact_page = " ".join(source_text.split())
                        if fragment not in compact_page:
                            raise AIResponseValidationError(
                                "Evidence fragment is not present in the source page."
                            )
                        evidence = ExtractedEvidence(
                            product_id=product.id,
                            ai_extraction_run_id=current.id,
                            document_id=current.document_id,
                            page_number=evidence_item.page,
                            text_fragment=fragment,
                            confidence=ConfidenceScore(evidence_item.confidence),
                            model=result.model,
                            prompt_version=current.prompt_version,
                        )
                        coordinates = evidence_item.coordinates
                        reference = EvidenceReference(
                            evidence_id=evidence.id,
                            page_number=evidence_item.page,
                            x0=coordinates.x0 if coordinates else None,
                            y0=coordinates.y0 if coordinates else None,
                            x1=coordinates.x1 if coordinates else None,
                            y1=coordinates.y1 if coordinates else None,
                        )
                        uow.catalogs.add_evidence(evidence, reference)

                current.complete(
                    provider_response_id=result.provider_response_id,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    estimated_cost_usd=result.estimated_cost_usd,
                    duration_ms=result.duration_ms,
                    products_detected=len(created_products),
                    raw_response=result.payload,
                )
                uow.catalogs.update_run(current)
                uow.audit_events.append(
                    catalog_event(
                        current.id,
                        "AIExtractionCompleted",
                        aggregate_type="ai_extraction",
                        tender_id=str(current.tender_id),
                        document_id=str(current.document_id),
                        products_detected=len(created_products),
                        input_tokens=result.input_tokens,
                        output_tokens=result.output_tokens,
                        estimated_cost_usd=str(result.estimated_cost_usd),
                        duration_ms=result.duration_ms,
                    )
                )
                uow.audit_events.append(
                    catalog_event(
                        current.tender_id,
                        "CatalogNormalized",
                        products_normalized=len(created_products),
                        ai_extraction_run_id=str(current.id),
                    )
                )
                uow.audit_events.append(
                    catalog_event(
                        current.tender_id,
                        "CatalogReviewStarted",
                        products_pending_review=len(created_products),
                        ai_extraction_run_id=str(current.id),
                    )
                )
                uow.commit()
                logger.info(
                    "ai_catalog_extraction_completed",
                    extra={
                        "tender_id": str(current.tender_id),
                        "document_id": str(current.document_id),
                        "ai_extraction_run_id": str(current.id),
                        "model": current.model,
                        "prompt_version": current.prompt_version,
                        "input_tokens": current.input_tokens,
                        "output_tokens": current.output_tokens,
                        "estimated_cost_usd": str(current.estimated_cost_usd),
                        "products_detected": current.products_detected,
                        "duration_ms": current.duration_ms,
                    },
                )
                return current.id
        except Exception as exc:
            validation_errors = [str(exc)] if isinstance(exc, AIResponseValidationError) else []
            with self._uow_factory() as uow:
                failed = uow.catalogs.get_run(run.id, for_update=True)
                if failed is not None:
                    failed.fail(exc, validation_errors=validation_errors)
                    uow.catalogs.update_run(failed)
                    uow.commit()
            logger.exception(
                "ai_catalog_extraction_failed",
                extra={"ai_extraction_run_id": str(run.id), "document_id": str(run.document_id)},
            )
            if isinstance(exc, (AIResponseValidationError, AIExtractionFailure)):
                raise
            raise AIExtractionFailure(str(exc)) from exc


class GetTenderCatalog:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, tender_id: UUID) -> TenderCatalogResponse:
        with self._uow_factory() as uow:
            if uow.tenders.get_by_id(tender_id) is None:
                raise TenderNotFound("Tender was not found.")
            products = uow.catalogs.list_products(tender_id)
            responses = tuple(_product_response(uow, product) for product in products)
            runs = uow.catalogs.list_runs(tender_id)
            latest = uow.catalogs.get_latest_snapshot(tender_id)
        total = len(products)
        edited = sum(product.manual_edit_count > 0 for product in products)
        metrics = CatalogMetricsResponse(
            products_total=total,
            products_pending_review=sum(
                product.status is ProductStatus.PENDING_REVIEW for product in products
            ),
            products_approved=sum(product.status is ProductStatus.APPROVED for product in products),
            products_rejected=sum(product.status is ProductStatus.REJECTED for product in products),
            average_confidence=(
                round(sum(product.confidence.value for product in products) / total, 4)
                if total
                else 0.0
            ),
            manual_edit_percentage=round((edited / total) * 100, 2) if total else 0.0,
            input_tokens=sum(run.input_tokens for run in runs),
            output_tokens=sum(run.output_tokens for run in runs),
            estimated_cost_usd=sum(
                (run.estimated_cost_usd for run in runs), Decimal("0")
            ),
        )
        return TenderCatalogResponse(
            tender_id=tender_id,
            products=responses,
            metrics=metrics,
            latest_snapshot_id=latest.id if latest else None,
            latest_snapshot_version=latest.version if latest else None,
        )


class GetCatalogProduct:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, product_id: UUID) -> CatalogProductResponse:
        with self._uow_factory() as uow:
            product = uow.catalogs.get_product(product_id)
            if product is None:
                raise CatalogProductNotFound("Catalog product was not found.")
            return _product_response(uow, product)


class UpdateCatalogProduct:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(
        self,
        product_id: UUID,
        *,
        action: str,
        reviewer_user_id: UUID,
        changes: dict,
        rejection_reason: str | None = None,
    ) -> CatalogProductResponse:
        with self._uow_factory() as uow:
            product = uow.catalogs.get_product(product_id)
            if product is None:
                raise CatalogProductNotFound("Catalog product was not found.")
            if not uow.users.exists(reviewer_user_id):
                raise InvalidCatalogState("Catalog reviewer does not exist.")
            before = _product_payload(product)
            if action == "edit":
                allowed = {
                    "name",
                    "description",
                    "quantity",
                    "unit",
                    "category",
                    "specifications",
                    "observations",
                }
                filtered = {key: value for key, value in changes.items() if key in allowed}
                product.edit(reviewer_user_id=reviewer_user_id, **filtered)
            elif action == "approve":
                product.approve(reviewer_user_id)
                uow.audit_events.append(
                    catalog_event(
                        product.id,
                        "ProductApproved",
                        aggregate_type="catalog_product",
                        tender_id=str(product.tender_id),
                        reviewer_user_id=str(reviewer_user_id),
                    )
                )
            elif action == "reject":
                product.reject(reviewer_user_id, rejection_reason or "")
                uow.audit_events.append(
                    catalog_event(
                        product.id,
                        "ProductRejected",
                        aggregate_type="catalog_product",
                        tender_id=str(product.tender_id),
                        reviewer_user_id=str(reviewer_user_id),
                        reason=product.rejection_reason,
                    )
                )
            else:
                raise InvalidCatalogState("Unsupported catalog product action.")
            updated = uow.catalogs.update_product(product)
            after = _product_payload(updated)
            changed_fields = [key for key in after if before.get(key) != after.get(key)]
            uow.catalogs.add_revision(
                product.id,
                reviewer_user_id,
                before,
                after,
                changed_fields,
            )
            uow.commit()
            return _product_response(uow, updated)


class ApproveTenderCatalog:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, tender_id: UUID, approved_by_user_id: UUID) -> CatalogSnapshotResponse:
        with self._uow_factory() as uow:
            if uow.tenders.get_by_id(tender_id) is None:
                raise TenderNotFound("Tender was not found.")
            if not uow.users.exists(approved_by_user_id):
                raise InvalidCatalogState("Catalog approver does not exist.")
            products = uow.catalogs.list_products(tender_id)
            if not products:
                raise InvalidCatalogState("Tender catalog has no products.")
            unresolved = [
                product
                for product in products
                if product.status not in {ProductStatus.APPROVED, ProductStatus.REJECTED}
            ]
            if unresolved:
                raise InvalidCatalogState(
                    "All products must be approved or rejected before catalog approval."
                )
            approved = [product for product in products if product.status is ProductStatus.APPROVED]
            if not approved:
                raise InvalidCatalogState("Approved catalog must contain at least one product.")
            latest = uow.catalogs.get_latest_snapshot(tender_id)
            snapshot = uow.catalogs.create_snapshot(
                CatalogSnapshot(
                    tender_id=tender_id,
                    version=(latest.version + 1) if latest else 1,
                    approved_by_user_id=approved_by_user_id,
                    products=tuple(product.snapshot_payload() for product in approved),
                )
            )
            uow.audit_events.append(
                catalog_event(
                    tender_id,
                    "CatalogApproved",
                    snapshot_id=str(snapshot.id),
                    version=snapshot.version,
                    approved_by_user_id=str(approved_by_user_id),
                    approved_products=len(approved),
                    rejected_products=sum(
                        product.status is ProductStatus.REJECTED for product in products
                    ),
                )
            )
            uow.commit()
        return CatalogSnapshotResponse(
            id=snapshot.id,
            tender_id=snapshot.tender_id,
            version=snapshot.version,
            approved_by_user_id=snapshot.approved_by_user_id,
            products=snapshot.products,
            created_at=snapshot.created_at,
        )
