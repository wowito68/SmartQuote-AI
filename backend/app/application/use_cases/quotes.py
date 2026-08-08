import hashlib
import json
import logging
from contextlib import suppress
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from app.application.dtos.quotes import (
    ComparisonResponse,
    QuoteItemResponse,
    QuoteResponse,
    QuoteReviewCommand,
    UploadQuoteCommand,
)
from app.application.exceptions import TenderNotFound
from app.application.ports.ai_extraction_service import AIExtractionRequest, AIExtractionService
from app.application.ports.document_text_extractor import DocumentTextExtractor
from app.application.ports.file_storage import FileStorage
from app.application.ports.prompt_registry import PromptRegistry
from app.application.ports.quote_analysis_queue import QuoteAnalysisQueue
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.application.services.comparison_engine import ComparisonEngine
from app.application.services.document_validation import DocumentFileValidator
from app.domain.comparisons.entities import ComparisonRun
from app.domain.documents.entities import PDF_MIME_TYPE
from app.domain.quotes.entities import Quote, QuoteExtractionRun, QuoteItem
from app.domain.quotes.events import quote_event
from app.domain.quotes.exceptions import (
    ComparisonNotFound,
    ComparisonNotReady,
    DuplicateQuote,
    InvalidQuoteState,
    QuoteExtractionFailure,
    QuoteNotFound,
)
from app.domain.quotes.value_objects import QuoteExtractionRunStatus, QuoteStatus
from app.domain.quotes.workflow import (
    mark_product_compared,
    mark_rfq_responded,
    mark_supplier_responded,
)
from app.domain.rfqs.value_objects import RfqStatus
from app.domain.suppliers.exceptions import SupplierNotFound
from app.domain.suppliers.value_objects import SupplierStatus
from app.domain.tenders.value_objects import TenderStatus

logger = logging.getLogger(__name__)


def _schema_hash(schema: dict) -> str:
    payload = json.dumps(schema, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def _quote_response(uow, quote: Quote) -> QuoteResponse:
    items = tuple(
        QuoteItemResponse(
            id=item.id,
            catalog_product_id=item.catalog_product_id,
            product_name=item.product_name,
            brand=item.brand,
            model=item.model,
            quantity=item.quantity,
            unit_price=item.unit_price,
            total_price=item.total_price,
            currency=item.currency,
            delivery_days=item.delivery_days,
            technical_compliance=item.technical_compliance,
            notes=item.notes,
            source_page=item.source_page,
            evidence_fragment=item.evidence_fragment,
            confidence=item.confidence,
        )
        for item in uow.quotes.list_items(quote.id)
    )
    return QuoteResponse(
        id=quote.id,
        tender_id=quote.tender_id,
        tender_supplier_id=quote.tender_supplier_id,
        supplier_id=quote.supplier_id,
        original_file_name=quote.original_file_name,
        file_hash=quote.file_hash,
        file_size=quote.file_size,
        mime_type=quote.mime_type,
        status=quote.status,
        version=quote.version,
        manual_edit_count=quote.manual_edit_count,
        reviewed_by_user_id=quote.reviewed_by_user_id,
        reviewed_at=quote.reviewed_at,
        rejection_reason=quote.rejection_reason,
        last_error=quote.last_error,
        items=items,
        created_at=quote.created_at,
        updated_at=quote.updated_at,
    )


def _comparison_response(item: ComparisonRun) -> ComparisonResponse:
    return ComparisonResponse(
        id=item.id,
        tender_id=item.tender_id,
        catalog_snapshot_id=item.catalog_snapshot_id,
        comparison_key=item.comparison_key,
        approved_quotes_version=item.approved_quotes_version,
        scoring_config_version=item.scoring_config_version,
        rows=item.rows,
        recommendation=item.recommendation,
        generated_by_user_id=item.generated_by_user_id,
        created_at=item.created_at,
    )


def _decimal(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise QuoteExtractionFailure(
            "AI quote response contains an invalid numeric value."
        ) from exc
    if not result.is_finite() or result < 0:
        raise QuoteExtractionFailure("AI quote response contains an invalid numeric value.")
    return result


def _normalized_name(value: str) -> str:
    return " ".join(value.casefold().split())


def _match_catalog_product(snapshot_products: tuple[dict, ...], name: str) -> UUID | None:
    candidate = _normalized_name(name)
    exact: list[UUID] = []
    partial: list[UUID] = []
    for product in snapshot_products:
        product_id = product.get("product_id")
        product_name = str(product.get("name") or "")
        if not product_id or not product_name:
            continue
        normalized = _normalized_name(product_name)
        if normalized == candidate:
            exact.append(UUID(str(product_id)))
        elif len(candidate) >= 5 and (candidate in normalized or normalized in candidate):
            partial.append(UUID(str(product_id)))
    if len(exact) == 1:
        return exact[0]
    if not exact and len(partial) == 1:
        return partial[0]
    return None


def _advance_to_quote_analysis(
    tender,
    *,
    catalog_ready: bool,
    supplier_ready: bool,
    rfq_sent: bool,
) -> None:
    if tender.status is TenderStatus.CATALOG_REVIEW and catalog_ready:
        tender.change_status(TenderStatus.SUPPLIER_REVIEW)
    if tender.status is TenderStatus.SUPPLIER_REVIEW and supplier_ready:
        tender.change_status(TenderStatus.RFQ_READY)
    if tender.status is TenderStatus.RFQ_READY and rfq_sent:
        tender.change_status(TenderStatus.WAITING_QUOTES)
    if tender.status is TenderStatus.WAITING_QUOTES:
        tender.change_status(TenderStatus.QUOTE_ANALYSIS)


class UploadSupplierQuote:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        file_storage: FileStorage,
        queue: QuoteAnalysisQueue,
        *,
        maximum_size_bytes: int,
    ) -> None:
        self._uow_factory = uow_factory
        self._file_storage = file_storage
        self._queue = queue
        self._validator = DocumentFileValidator(
            maximum_size_bytes=maximum_size_bytes,
            maximum_files_per_upload=1,
        )

    def execute(self, command: UploadQuoteCommand) -> QuoteResponse:
        validated = self._validator.validate(command.file)
        storage_key: str | None = None
        with self._uow_factory() as uow:
            tender = uow.tenders.get_by_id(command.tender_id)
            if tender is None:
                raise TenderNotFound("Tender was not found.")
            tender_supplier = uow.suppliers.get_tender_supplier(command.tender_supplier_id)
            if tender_supplier is None or tender_supplier.tender_id != command.tender_id:
                raise SupplierNotFound("Tender supplier was not found.")
            if tender_supplier.status not in {
                SupplierStatus.APPROVED,
                SupplierStatus.CONTACTED,
                SupplierStatus.RESPONDED,
            }:
                raise InvalidQuoteState("Quotes can only be loaded for approved suppliers.")
            if not uow.users.exists(command.uploaded_by_user_id):
                raise InvalidQuoteState("Quote uploader user does not exist.")
            sent_rfqs = [
                rfq
                for rfq in uow.rfqs.list_rfqs(command.tender_id)
                if rfq.tender_supplier_id == tender_supplier.id
                and rfq.status in {RfqStatus.SENT, RfqStatus.DELIVERED, RfqStatus.RESPONDED}
            ]
            if not sent_rfqs:
                raise InvalidQuoteState("A quote requires a previously sent RFQ for this supplier.")
            if uow.quotes.find_duplicate(
                command.tender_id, tender_supplier.supplier_id, validated.file_hash.value
            ):
                raise DuplicateQuote(
                    "The same supplier quote is already registered for this tender."
                )
            quote_id = uuid4()
            try:
                storage_key = self._file_storage.store(
                    command.tender_id,
                    quote_id,
                    validated.content,
                )
                quote = Quote(
                    id=quote_id,
                    tender_id=command.tender_id,
                    tender_supplier_id=tender_supplier.id,
                    supplier_id=tender_supplier.supplier_id,
                    original_file_name=validated.original_file_name,
                    storage_key=storage_key,
                    mime_type=PDF_MIME_TYPE,
                    file_size=validated.file_size,
                    file_hash=validated.file_hash.value,
                    uploaded_by_user_id=command.uploaded_by_user_id,
                )
                quote.start_validation()
                quote = uow.quotes.create_quote(quote)
                mark_supplier_responded(tender_supplier)
                uow.suppliers.update_tender_supplier(tender_supplier)
                for rfq in sent_rfqs:
                    mark_rfq_responded(rfq)
                    uow.rfqs.update_rfq(rfq)
                _advance_to_quote_analysis(
                    tender,
                    catalog_ready=uow.catalogs.get_latest_snapshot(command.tender_id) is not None,
                    supplier_ready=True,
                    rfq_sent=True,
                )
                uow.tenders.update(tender)
                uow.audit_events.append(
                    quote_event(
                        quote.id,
                        "QuoteUploaded",
                        tender_id=str(quote.tender_id),
                        supplier_id=str(quote.supplier_id),
                        uploaded_by_user_id=str(command.uploaded_by_user_id),
                        file_hash=quote.file_hash,
                        file_size=quote.file_size,
                    )
                )
                uow.commit()
                response = _quote_response(uow, quote)
            except Exception:
                uow.rollback()
                if storage_key:
                    with suppress(Exception):
                        self._file_storage.delete(storage_key)
                raise
        try:
            self._queue.enqueue(quote.id, command.correlation_id)
        except Exception as exc:
            with self._uow_factory() as uow:
                current = uow.quotes.get_quote(quote.id, for_update=True)
                if current is not None:
                    current.record_error(exc)
                    uow.quotes.update_quote(current)
                    uow.commit()
            raise QuoteExtractionFailure("Unable to queue quote analysis.") from exc
        return response


class ProcessSupplierQuote:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        file_storage: FileStorage,
        text_extractor: DocumentTextExtractor,
        ai_service: AIExtractionService,
        prompt_registry: PromptRegistry,
        *,
        prompt_version: str,
        model: str,
        temperature: float,
    ) -> None:
        self._uow_factory = uow_factory
        self._file_storage = file_storage
        self._text_extractor = text_extractor
        self._ai_service = ai_service
        self._prompt_registry = prompt_registry
        self._prompt_version = prompt_version
        self._model = model
        self._temperature = temperature

    def execute(self, quote_id: UUID) -> UUID:
        prompt = self._prompt_registry.get("quote_extraction", self._prompt_version)
        schema_hash = _schema_hash(prompt.output_schema)
        with self._uow_factory() as uow:
            quote = uow.quotes.get_quote(quote_id, for_update=True)
            if quote is None:
                raise QuoteNotFound("Quote was not found.")
            key_data = "|".join(
                (
                    quote.file_hash,
                    str(quote.tender_id),
                    str(quote.supplier_id),
                    self._text_extractor.version,
                    prompt.version,
                    self._model,
                    schema_hash,
                )
            )
            key = hashlib.sha256(key_data.encode()).hexdigest()
            existing = uow.quotes.get_run_by_key(quote.id, key)
            if existing and existing.status in {
                QuoteExtractionRunStatus.COMPLETED,
                QuoteExtractionRunStatus.REUSED,
            } and uow.quotes.list_items(quote.id):
                return quote.id
            if existing is None:
                run = uow.quotes.create_run(
                    QuoteExtractionRun(
                        quote_id=quote.id,
                        tender_id=quote.tender_id,
                        supplier_id=quote.supplier_id,
                        idempotency_key=key,
                        extractor_version=self._text_extractor.version,
                        prompt_version=prompt.version,
                        model=self._model,
                        schema_version=prompt.schema_version,
                        schema_hash=schema_hash,
                    )
                )
            else:
                run = existing
                run.restart()
            if quote.status is QuoteStatus.VALIDATING:
                quote.start_extraction()
            elif quote.status is not QuoteStatus.EXTRACTING:
                if uow.quotes.list_items(quote.id):
                    return quote.id
                raise InvalidQuoteState("Quote is not ready for extraction.")
            run.start()
            uow.quotes.update_quote(quote)
            run = uow.quotes.update_run(run)
            storage_key = quote.storage_key
            uow.audit_events.append(
                quote_event(
                    run.id,
                    "QuoteExtractionStarted",
                    aggregate_type="quote_extraction",
                    quote_id=str(quote.id),
                    tender_id=str(quote.tender_id),
                    model=run.model,
                    prompt_version=run.prompt_version,
                    schema_version=run.schema_version,
                    extractor_version=run.extractor_version,
                )
            )
            uow.commit()

        try:
            text_result = self._text_extractor.extract(self._file_storage.read(storage_key))
            pages = tuple(
                {"page_number": page.page_number, "text": page.text}
                for page in text_result.pages
            )
            if not pages or not any(str(page["text"]).strip() for page in pages):
                raise QuoteExtractionFailure("Quote PDF does not contain extractable text.")
            ai_result = self._ai_service.extract(
                AIExtractionRequest(
                    prompt=prompt,
                    model=self._model,
                    temperature=self._temperature,
                    document_id=str(quote_id),
                    pages=pages,
                )
            )
            raw_items = ai_result.payload.get("items")
            if not isinstance(raw_items, list) or not raw_items:
                raise QuoteExtractionFailure("AI quote response must contain at least one item.")
            page_text = {
                int(page["page_number"]): " ".join(str(page["text"]).split()) for page in pages
            }
            with self._uow_factory() as uow:
                current = uow.quotes.get_quote(quote_id, for_update=True)
                current_run = uow.quotes.get_run(run.id, for_update=True)
                if current is None or current_run is None:
                    raise QuoteNotFound("Quote extraction state was not found.")
                snapshot = uow.catalogs.get_latest_snapshot(current.tender_id)
                if snapshot is None:
                    raise InvalidQuoteState("Quote normalization requires an approved catalog.")
                items: list[QuoteItem] = []
                for raw in raw_items:
                    if not isinstance(raw, dict):
                        raise QuoteExtractionFailure("AI quote item must be an object.")
                    name = str(raw.get("product_name") or "").strip()
                    if not name:
                        raise QuoteExtractionFailure("AI quote item is missing product_name.")
                    evidence = raw.get("evidence") or {}
                    page = int(evidence.get("page") or 0)
                    fragment = " ".join(str(evidence.get("fragment") or "").split())
                    if page not in page_text or not fragment or fragment not in page_text[page]:
                        raise QuoteExtractionFailure(
                            "Quote evidence is not grounded in its source page."
                        )
                    items.append(
                        QuoteItem(
                            quote_id=current.id,
                            catalog_product_id=_match_catalog_product(snapshot.products, name),
                            product_name=name,
                            brand=raw.get("brand"),
                            model=raw.get("model"),
                            quantity=_decimal(raw.get("quantity")),
                            unit_price=_decimal(raw.get("unit_price")),
                            total_price=_decimal(raw.get("total_price")),
                            currency=raw.get("currency"),
                            delivery_days=(
                                int(raw["delivery_days"])
                                if raw.get("delivery_days") is not None
                                else None
                            ),
                            technical_compliance=raw.get("technical_compliance"),
                            notes=raw.get("notes"),
                            source_page=page,
                            evidence_fragment=fragment,
                            confidence=float(evidence.get("confidence") or 0),
                        )
                    )
                uow.quotes.replace_items(current.id, tuple(items))
                current.mark_extracted()
                current.mark_normalized()
                current.start_review()
                current.last_error = None
                uow.quotes.update_quote(current)
                current_run.complete(
                    provider_response_id=ai_result.provider_response_id,
                    input_tokens=ai_result.input_tokens,
                    output_tokens=ai_result.output_tokens,
                    estimated_cost_usd=ai_result.estimated_cost_usd,
                    raw_response=ai_result.payload,
                )
                uow.quotes.update_run(current_run)
                uow.audit_events.append(
                    quote_event(
                        current.id,
                        "QuoteExtractedAndNormalized",
                        tender_id=str(current.tender_id),
                        supplier_id=str(current.supplier_id),
                        extraction_run_id=str(current_run.id),
                        item_count=len(items),
                        input_tokens=ai_result.input_tokens,
                        output_tokens=ai_result.output_tokens,
                        estimated_cost_usd=str(ai_result.estimated_cost_usd),
                        model=ai_result.model,
                        prompt_version=current_run.prompt_version,
                        schema_version=current_run.schema_version,
                    )
                )
                uow.commit()
                return current.id
        except Exception as exc:
            with self._uow_factory() as uow:
                current = uow.quotes.get_quote(quote_id, for_update=True)
                failed_run = uow.quotes.get_run(run.id, for_update=True)
                if current is not None:
                    current.record_error(exc)
                    uow.quotes.update_quote(current)
                if failed_run is not None:
                    failed_run.fail(exc)
                    uow.quotes.update_run(failed_run)
                uow.commit()
            logger.exception("quote_analysis_failed", extra={"quote_id": str(quote_id)})
            if isinstance(exc, QuoteExtractionFailure):
                raise
            raise QuoteExtractionFailure(str(exc)) from exc


class GetQuote:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, quote_id: UUID) -> QuoteResponse:
        with self._uow_factory() as uow:
            quote = uow.quotes.get_quote(quote_id)
            if quote is None:
                raise QuoteNotFound("Quote was not found.")
            return _quote_response(uow, quote)


class ListTenderQuotes:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, tender_id: UUID) -> tuple[QuoteResponse, ...]:
        with self._uow_factory() as uow:
            if uow.tenders.get_by_id(tender_id) is None:
                raise TenderNotFound("Tender was not found.")
            return tuple(_quote_response(uow, item) for item in uow.quotes.list_quotes(tender_id))


class ReviewQuote:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, quote_id: UUID, command: QuoteReviewCommand) -> QuoteResponse:
        with self._uow_factory() as uow:
            quote = uow.quotes.get_quote(quote_id, for_update=True)
            if quote is None:
                raise QuoteNotFound("Quote was not found.")
            if not uow.users.exists(command.reviewer_user_id):
                raise InvalidQuoteState("Quote reviewer user does not exist.")
            if command.action == "approve":
                quote.approve(command.reviewer_user_id)
                event_name = "QuoteApproved"
            elif command.action == "reject":
                quote.reject(command.reviewer_user_id, command.rejection_reason or "")
                event_name = "QuoteRejected"
            else:
                raise InvalidQuoteState("Unsupported quote review action.")
            quote = uow.quotes.update_quote(quote)
            uow.audit_events.append(
                quote_event(
                    quote.id,
                    event_name,
                    tender_id=str(quote.tender_id),
                    supplier_id=str(quote.supplier_id),
                    reviewer_user_id=str(command.reviewer_user_id),
                    reason=quote.rejection_reason,
                )
            )
            uow.commit()
            return _quote_response(uow, quote)


class GenerateTenderComparison:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        engine: ComparisonEngine,
        *,
        scoring_config_version: str,
    ) -> None:
        self._uow_factory = uow_factory
        self._engine = engine
        self._scoring_config_version = scoring_config_version

    def execute(self, tender_id: UUID, generated_by_user_id: UUID) -> ComparisonResponse:
        with self._uow_factory() as uow:
            tender = uow.tenders.get_by_id(tender_id)
            if tender is None:
                raise TenderNotFound("Tender was not found.")
            if not uow.users.exists(generated_by_user_id):
                raise ComparisonNotReady("Comparison generator user does not exist.")
            snapshot = uow.catalogs.get_latest_snapshot(tender_id)
            if snapshot is None:
                raise ComparisonNotReady("Comparison requires an approved catalog.")
            quotes = uow.quotes.list_quotes_by_status(
                tender_id,
                {QuoteStatus.APPROVED, QuoteStatus.INCLUDED_IN_COMPARISON},
            )
            if not quotes:
                raise ComparisonNotReady("Comparison requires at least one approved quote.")
            version_payload = [
                f"{item.id}:{item.version}:{item.file_hash}"
                for item in sorted(quotes, key=lambda value: str(value.id))
            ]
            approved_quotes_version = hashlib.sha256("|".join(version_payload).encode()).hexdigest()
            key_data = "|".join(
                (
                    str(tender_id),
                    str(snapshot.id),
                    str(snapshot.version),
                    approved_quotes_version,
                    self._scoring_config_version,
                )
            )
            key = hashlib.sha256(key_data.encode()).hexdigest()
            existing = uow.quotes.get_comparison_by_key(tender_id, key)
            if existing is not None:
                return _comparison_response(existing)

            entries: list[tuple[str, str, QuoteItem]] = []
            for quote in quotes:
                supplier = uow.suppliers.get_supplier(quote.supplier_id)
                if supplier is None:
                    raise SupplierNotFound("Quote supplier was not found.")
                supplier_name = (
                    supplier.trade_name
                    or supplier.legal_name
                    or supplier.normalized_domain
                    or str(supplier.id)
                )
                entries.extend(
                    (str(supplier.id), supplier_name, item)
                    for item in uow.quotes.list_items(quote.id)
                )
            rows, recommendation = self._engine.build(entries)
            comparison = uow.quotes.create_comparison(
                ComparisonRun(
                    tender_id=tender_id,
                    catalog_snapshot_id=snapshot.id,
                    comparison_key=key,
                    approved_quotes_version=approved_quotes_version,
                    scoring_config_version=self._scoring_config_version,
                    rows=rows,
                    recommendation=recommendation,
                    generated_by_user_id=generated_by_user_id,
                )
            )
            product_ids: set[UUID] = set()
            for quote in quotes:
                if quote.status is QuoteStatus.APPROVED:
                    quote.include_in_comparison()
                    uow.quotes.update_quote(quote)
                product_ids.update(
                    item.catalog_product_id
                    for item in uow.quotes.list_items(quote.id)
                    if item.catalog_product_id is not None
                )
            for product_id in product_ids:
                product = uow.catalogs.get_product(product_id)
                if product is not None:
                    mark_product_compared(product)
                    uow.catalogs.update_product(product)
            if tender.status is TenderStatus.QUOTE_ANALYSIS:
                tender.change_status(TenderStatus.COMPARISON_READY)
                uow.tenders.update(tender)
            uow.audit_events.append(
                quote_event(
                    comparison.id,
                    "ComparisonGenerated",
                    aggregate_type="comparison",
                    tender_id=str(tender_id),
                    catalog_snapshot_id=str(snapshot.id),
                    approved_quotes_version=approved_quotes_version,
                    scoring_config_version=self._scoring_config_version,
                    row_count=len(rows),
                )
            )
            uow.audit_events.append(
                quote_event(
                    comparison.id,
                    "RecommendationGenerated",
                    aggregate_type="comparison",
                    tender_id=str(tender_id),
                    recommended_supplier_id=recommendation["recommended_supplier_id"],
                    score=recommendation["score"],
                    human_review_required=True,
                    warnings=recommendation["warnings"],
                )
            )
            uow.commit()
            return _comparison_response(comparison)


class GetTenderComparison:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, tender_id: UUID) -> ComparisonResponse:
        with self._uow_factory() as uow:
            comparison = uow.quotes.get_latest_comparison(tender_id)
            if comparison is None:
                raise ComparisonNotFound("Tender comparison was not found.")
            return _comparison_response(comparison)
