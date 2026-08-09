import hashlib
import json
import logging
from contextlib import suppress
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from app.application.dtos.quotes import (
    ComparisonResponse,
    QuoteDocumentResponse,
    QuoteEvidenceResponse,
    QuoteExtractionRunResponse,
    QuoteItemResponse,
    QuoteProcessingStatusResponse,
    QuoteResponse,
    QuoteReviewCommand,
    QuoteUploadResponse,
    UpdateQuoteItemCommand,
    UploadQuoteCommand,
    UploadQuoteDocumentCommand,
)
from app.application.exceptions import TenderNotFound
from app.application.ports.ai_extraction_service import AIExtractionRequest, AIExtractionService
from app.application.ports.document_text_extractor import DocumentTextExtractor
from app.application.ports.file_storage import FileStorage
from app.application.ports.prompt_registry import PromptRegistry
from app.application.ports.quote_analysis_queue import QuoteAnalysisQueue
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.application.services.comparison_engine import ComparisonEngine
from app.application.services.quote_document_validation import QuoteDocumentValidator
from app.application.services.quote_matching import QuoteProductMatcher, TechnicalComplianceEvaluator
from app.application.services.quote_normalization import QuoteNormalizer
from app.domain.catalog.exceptions import AIExtractionFailure
from app.domain.catalog.value_objects import ProductStatus
from app.domain.comparisons.entities import ComparisonRun
from app.domain.documents.exceptions import DocumentStorageFailure
from app.domain.quotes.entities import (
    Quote,
    QuoteDocument,
    QuoteEvidenceReference,
    QuoteExtractionRun,
    QuoteItem,
    QuoteItemRevision,
    QuoteTaskRecord,
)
from app.domain.quotes.events import quote_event
from app.domain.quotes.exceptions import (
    ComparisonNotFound,
    ComparisonNotReady,
    DuplicateQuote,
    InvalidQuoteState,
    QuoteDocumentNotFound,
    QuoteExtractionFailure,
    QuoteItemNotFound,
    QuoteNotFound,
    QuoteProviderError,
    QuoteStorageError,
    RetryableQuoteExtractionFailure,
)
from app.domain.quotes.value_objects import (
    ComplianceStatus,
    EvidenceFindingStatus,
    ProductMatchStatus,
    QuoteExtractionRunStatus,
    QuoteStatus,
    QuoteTaskStatus,
)
from app.domain.quotes.workflow import mark_product_compared, mark_rfq_responded, mark_supplier_responded
from app.domain.rfqs.value_objects import RfqStatus
from app.domain.shared.exceptions import ValidationError
from app.domain.suppliers.exceptions import SupplierNotFound
from app.domain.suppliers.value_objects import SupplierStatus
from app.domain.tenders.value_objects import TenderStatus
from app.infrastructure.extraction.quote_document_extractor import MultiFormatQuoteDocumentExtractor

logger = logging.getLogger(__name__)


def _schema_hash(schema: dict) -> str:
    payload = json.dumps(schema, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def _decimal(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise QuoteExtractionFailure("AI quote response contains an invalid numeric value.") from exc
    if not result.is_finite() or result < 0:
        raise QuoteExtractionFailure("AI quote response contains an invalid numeric value.")
    return result


def _parse_datetime(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise QuoteExtractionFailure("AI quote response contains an invalid date.") from exc
    if result.tzinfo is None:
        result = result.replace(tzinfo=UTC)
    return result.astimezone(UTC)


def _document_response(document: QuoteDocument) -> QuoteDocumentResponse:
    return QuoteDocumentResponse(
        id=document.id,
        quote_id=document.quote_id,
        original_file_name=document.original_file_name,
        mime_type=document.mime_type,
        file_size=document.file_size,
        file_hash=document.file_hash,
        document_type=document.document_type,
        processing_status=document.processing_status,
        extractor_name=document.extractor_name,
        extractor_version=document.extractor_version,
        last_error=document.last_error,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def _run_response(run: QuoteExtractionRun) -> QuoteExtractionRunResponse:
    return QuoteExtractionRunResponse(
        id=run.id,
        quote_document_id=run.quote_document_id,
        run_number=run.run_number,
        provider=run.provider,
        model=run.model,
        prompt_version=run.prompt_version,
        schema_version=run.schema_version,
        extractor_name=run.extractor_name,
        extractor_version=run.extractor_version,
        status=run.status,
        input_tokens=run.input_tokens,
        output_tokens=run.output_tokens,
        estimated_cost_usd=run.estimated_cost_usd,
        duration_ms=run.duration_ms,
        is_approved_source=run.is_approved_source,
        error_type=run.error_type,
        error_message=run.error_message,
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
    )


def _item_response(item: QuoteItem) -> QuoteItemResponse:
    return QuoteItemResponse(
        id=item.id,
        catalog_product_id=item.catalog_product_id,
        extraction_run_id=item.extraction_run_id,
        product_name=item.product_name,
        description=item.description,
        brand=item.brand,
        model=item.model,
        quantity=item.quantity,
        unit=item.unit,
        unit_price=item.unit_price,
        total_price=item.total_price,
        currency=item.currency,
        delivery_days=item.delivery_days,
        technical_compliance=item.technical_compliance,
        compliance_status=item.compliance_status,
        quoted_specifications=dict(item.quoted_specifications),
        match_status=item.match_status,
        match_score=item.match_score,
        match_reason=item.match_reason,
        warnings=item.warnings,
        notes=item.notes,
        source_evidence_id=item.source_evidence_id,
        source_page=item.source_page,
        evidence_fragment=item.evidence_fragment,
        confidence=item.confidence,
        original_extracted=dict(item.original_extracted),
    )


def _quote_response(uow, quote: Quote) -> QuoteResponse:
    return QuoteResponse(
        id=quote.id,
        tender_id=quote.tender_id,
        tender_supplier_id=quote.tender_supplier_id,
        supplier_id=quote.supplier_id,
        rfq_request_id=quote.rfq_request_id,
        original_file_name=quote.original_file_name,
        file_hash=quote.file_hash,
        file_size=quote.file_size,
        mime_type=quote.mime_type,
        status=quote.status,
        currency=quote.currency,
        subtotal_amount=quote.subtotal_amount,
        tax_amount=quote.tax_amount,
        total_amount=quote.total_amount,
        delivery_time_days=quote.delivery_time_days,
        commercial_terms=quote.commercial_terms,
        valid_until=quote.valid_until,
        received_at=quote.received_at,
        approved_extraction_run_id=quote.approved_extraction_run_id,
        version=quote.version,
        manual_edit_count=quote.manual_edit_count,
        reviewed_by_user_id=quote.reviewed_by_user_id,
        reviewed_at=quote.reviewed_at,
        rejection_reason=quote.rejection_reason,
        last_error=quote.last_error,
        items=tuple(_item_response(item) for item in uow.quotes.list_items(quote.id)),
        documents=tuple(_document_response(item) for item in uow.quotes.list_documents(quote.id)),
        extraction_runs=tuple(_run_response(item) for item in uow.quotes.list_runs(quote.id)),
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


def _advance_to_quote_analysis(tender, *, catalog_ready: bool, supplier_ready: bool, rfq_sent: bool) -> None:
    if tender.status is TenderStatus.CATALOG_REVIEW and catalog_ready:
        tender.change_status(TenderStatus.SUPPLIER_REVIEW)
    if tender.status is TenderStatus.SUPPLIER_REVIEW and supplier_ready:
        tender.change_status(TenderStatus.RFQ_READY)
    if tender.status is TenderStatus.RFQ_READY and rfq_sent:
        tender.change_status(TenderStatus.WAITING_QUOTES)
    if tender.status is TenderStatus.WAITING_QUOTES:
        tender.change_status(TenderStatus.QUOTE_ANALYSIS)


def _sent_rfqs(uow, tender_id: UUID, tender_supplier_id: UUID):
    return [
        rfq
        for rfq in uow.rfqs.list_rfqs(tender_id)
        if rfq.tender_supplier_id == tender_supplier_id
        and rfq.status in {RfqStatus.SENT, RfqStatus.DELIVERED, RfqStatus.RESPONDED}
    ]


class QueueQuoteProcessing:
    def __init__(self, uow_factory: UnitOfWorkFactory, queue: QuoteAnalysisQueue) -> None:
        self._uow_factory = uow_factory
        self._queue = queue

    def execute(
        self,
        quote_id: UUID,
        *,
        force_reprocess: bool = False,
        correlation_id: str | None = None,
    ) -> QuoteTaskRecord:
        correlation = correlation_id or f"quote:{quote_id}:{uuid4().hex}"
        with self._uow_factory() as uow:
            quote = uow.quotes.get_quote(quote_id, for_update=True)
            if quote is None:
                raise QuoteNotFound("Quote was not found.")
            existing = uow.quotes.get_task_by_correlation(correlation)
            if existing is not None:
                return existing
            if force_reprocess:
                quote.restart_processing()
                uow.audit_events.append(
                    quote_event(
                        quote.id,
                        "QuoteReprocessed",
                        correlation_id=correlation,
                        previous_version=quote.version,
                    )
                )
            elif quote.status is QuoteStatus.RECEIVED:
                quote.start_validation()
            elif quote.status not in {QuoteStatus.VALIDATING, QuoteStatus.EXTRACTING}:
                completed = [
                    run
                    for run in uow.quotes.list_runs(quote.id)
                    if run.status in {QuoteExtractionRunStatus.COMPLETED, QuoteExtractionRunStatus.REUSED}
                ]
                if completed and uow.quotes.list_items(quote.id):
                    latest = uow.quotes.get_latest_task(quote.id)
                    return latest or QuoteTaskRecord(quote.id, correlation, status=QuoteTaskStatus.SUCCEEDED)
                raise InvalidQuoteState("Quote is not ready to be queued for processing.")
            task = uow.quotes.create_task(
                QuoteTaskRecord(
                    quote_id=quote.id,
                    correlation_id=correlation,
                    force_reprocess=force_reprocess,
                )
            )
            uow.quotes.update_quote(quote)
            uow.commit()
        try:
            try:
                self._queue.enqueue(
                    quote_id,
                    correlation,
                    task_record_id=task.id,
                    force_reprocess=force_reprocess,
                )
            except TypeError:
                # Compatibility for Iteration 9 queue test doubles.
                self._queue.enqueue(quote_id, correlation)
        except Exception as exc:
            with self._uow_factory() as uow:
                current = uow.quotes.get_quote(quote_id, for_update=True)
                current_task = uow.quotes.get_task(task.id, for_update=True)
                if current_task is not None:
                    current_task.fail(exc, retryable=True)
                    uow.quotes.update_task(current_task)
                if current is not None:
                    current.mark_failed(exc)
                    uow.quotes.update_quote(current)
                uow.commit()
            raise RetryableQuoteExtractionFailure("Unable to queue quote analysis.") from exc
        return task


class UploadQuoteDocument:
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
        self._validator = QuoteDocumentValidator(maximum_size_bytes)

    def execute(self, command: UploadQuoteDocumentCommand) -> QuoteUploadResponse:
        validated = self._validator.validate(command.file)
        storage_key: str | None = None
        with self._uow_factory() as uow:
            tender = uow.tenders.get_by_id(command.tender_id)
            if tender is None:
                raise TenderNotFound("Tender was not found.")
            if tender.status in {TenderStatus.CLOSED, TenderStatus.CANCELLED}:
                raise InvalidQuoteState("Closed or cancelled tenders cannot receive quotes.")
            tender_supplier = uow.suppliers.find_tender_supplier(command.tender_id, command.supplier_id)
            if tender_supplier is None:
                raise SupplierNotFound("Supplier is not associated with this tender.")
            if tender_supplier.status not in {
                SupplierStatus.APPROVED,
                SupplierStatus.CONTACTED,
                SupplierStatus.RESPONDED,
            }:
                raise InvalidQuoteState("Quotes can only be received from approved suppliers.")
            if not uow.users.exists(command.uploaded_by_user_id):
                raise InvalidQuoteState("Quote uploader user does not exist.")
            sent_rfqs = _sent_rfqs(uow, command.tender_id, tender_supplier.id)
            if not sent_rfqs:
                raise InvalidQuoteState("A quote requires a previously sent RFQ for this supplier.")
            associated_rfq = None
            if command.rfq_request_id is not None:
                associated_rfq = uow.rfqs.get_rfq(command.rfq_request_id)
                if (
                    associated_rfq is None
                    or associated_rfq.tender_id != command.tender_id
                    or associated_rfq.supplier_id != command.supplier_id
                    or associated_rfq.status not in {RfqStatus.SENT, RfqStatus.DELIVERED, RfqStatus.RESPONDED}
                ):
                    raise InvalidQuoteState("Associated RFQ is not a sent RFQ for this supplier.")
            else:
                associated_rfq = sent_rfqs[-1]
            duplicate = uow.quotes.find_duplicate(
                command.tender_id,
                command.supplier_id,
                validated.file_hash,
            )
            if duplicate is not None:
                uow.audit_events.append(
                    quote_event(
                        duplicate.id,
                        "QuoteDuplicateDetected",
                        tender_id=str(command.tender_id),
                        supplier_id=str(command.supplier_id),
                        file_hash=validated.file_hash,
                        uploaded_by_user_id=str(command.uploaded_by_user_id),
                    )
                )
                uow.commit()
                return QuoteUploadResponse(_quote_response(uow, duplicate), True, False)
            quote_id = uuid4()
            try:
                storage_key = self._file_storage.store(command.tender_id, quote_id, validated.content)
                quote = Quote(
                    id=quote_id,
                    tender_id=command.tender_id,
                    tender_supplier_id=tender_supplier.id,
                    supplier_id=command.supplier_id,
                    rfq_request_id=associated_rfq.id if associated_rfq else None,
                    original_file_name=validated.original_file_name,
                    storage_key=storage_key,
                    mime_type=validated.mime_type,
                    file_size=validated.file_size,
                    file_hash=validated.file_hash,
                    uploaded_by_user_id=command.uploaded_by_user_id,
                )
                quote.start_validation()
                quote = uow.quotes.create_quote(quote)
                document = uow.quotes.create_document(
                    QuoteDocument(
                        quote_id=quote.id,
                        storage_key=storage_key,
                        original_file_name=validated.original_file_name,
                        mime_type=validated.mime_type,
                        file_size=validated.file_size,
                        file_hash=validated.file_hash,
                        document_type=validated.document_type,
                    )
                )
                mark_supplier_responded(tender_supplier)
                uow.suppliers.update_tender_supplier(tender_supplier)
                if associated_rfq is not None:
                    mark_rfq_responded(associated_rfq)
                    uow.rfqs.update_rfq(associated_rfq)
                _advance_to_quote_analysis(
                    tender,
                    catalog_ready=uow.catalogs.get_latest_snapshot(command.tender_id) is not None,
                    supplier_ready=True,
                    rfq_sent=True,
                )
                uow.tenders.update(tender)
                common = {
                    "tender_id": str(quote.tender_id),
                    "supplier_id": str(quote.supplier_id),
                    "rfq_request_id": str(quote.rfq_request_id) if quote.rfq_request_id else None,
                    "uploaded_by_user_id": str(command.uploaded_by_user_id),
                    "file_hash": quote.file_hash,
                    "file_size": quote.file_size,
                    "document_type": document.document_type.value,
                }
                uow.audit_events.append(quote_event(quote.id, "QuoteReceived", **common))
                uow.audit_events.append(
                    quote_event(
                        document.id,
                        "QuoteFileStored",
                        aggregate_type="quote_document",
                        quote_id=str(quote.id),
                        **common,
                    )
                )
                # Iteration 9 compatibility event.
                uow.audit_events.append(quote_event(quote.id, "QuoteUploaded", **common))
                uow.commit()
                response = _quote_response(uow, quote)
            except Exception:
                uow.rollback()
                if storage_key:
                    with suppress(Exception):
                        self._file_storage.delete(storage_key)
                raise
        queued = False
        if command.auto_process:
            QueueQuoteProcessing(self._uow_factory, self._queue).execute(
                quote_id,
                correlation_id=command.correlation_id,
            )
            queued = True
        with self._uow_factory() as uow:
            current = uow.quotes.get_quote(quote_id)
            if current is None:
                raise QuoteNotFound("Quote disappeared after upload.")
            return QuoteUploadResponse(_quote_response(uow, current), False, queued)


class UploadSupplierQuote:
    """Compatibility adapter for Iteration 9's tender-supplier upload endpoint."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        file_storage: FileStorage,
        queue: QuoteAnalysisQueue,
        *,
        maximum_size_bytes: int,
    ) -> None:
        self._uow_factory = uow_factory
        self._delegate = UploadQuoteDocument(
            uow_factory,
            file_storage,
            queue,
            maximum_size_bytes=maximum_size_bytes,
        )

    def execute(self, command: UploadQuoteCommand) -> QuoteResponse:
        with self._uow_factory() as uow:
            tender_supplier = uow.suppliers.get_tender_supplier(command.tender_supplier_id)
            if tender_supplier is None or tender_supplier.tender_id != command.tender_id:
                raise SupplierNotFound("Tender supplier was not found.")
            duplicate_hash = QuoteDocumentValidator(self._delegate._validator._maximum_size_bytes).validate(command.file).file_hash
            if uow.quotes.find_duplicate(command.tender_id, tender_supplier.supplier_id, duplicate_hash):
                raise DuplicateQuote("The same supplier quote is already registered for this tender.")
            supplier_id = tender_supplier.supplier_id
        result = self._delegate.execute(
            UploadQuoteDocumentCommand(
                tender_id=command.tender_id,
                supplier_id=supplier_id,
                rfq_request_id=command.rfq_request_id,
                uploaded_by_user_id=command.uploaded_by_user_id,
                file=command.file,
                correlation_id=command.correlation_id,
                auto_process=True,
            )
        )
        return result.quote


class AddQuoteDocument:
    def __init__(self, uow_factory: UnitOfWorkFactory, file_storage: FileStorage, *, maximum_size_bytes: int) -> None:
        self._uow_factory = uow_factory
        self._file_storage = file_storage
        self._validator = QuoteDocumentValidator(maximum_size_bytes)

    def execute(self, quote_id: UUID, file, uploaded_by_user_id: UUID) -> QuoteDocumentResponse:
        validated = self._validator.validate(file)
        storage_key: str | None = None
        with self._uow_factory() as uow:
            quote = uow.quotes.get_quote(quote_id, for_update=True)
            if quote is None:
                raise QuoteNotFound("Quote was not found.")
            if quote.status in {QuoteStatus.APPROVED, QuoteStatus.INCLUDED_IN_COMPARISON}:
                raise InvalidQuoteState("Approved quotes cannot receive additional documents silently.")
            if not uow.users.exists(uploaded_by_user_id):
                raise InvalidQuoteState("Quote document uploader user does not exist.")
            for existing in uow.quotes.list_documents(quote_id):
                if existing.file_hash == validated.file_hash:
                    return _document_response(existing)
            document_id = uuid4()
            try:
                storage_key = self._file_storage.store(quote.tender_id, document_id, validated.content)
                document = uow.quotes.create_document(
                    QuoteDocument(
                        id=document_id,
                        quote_id=quote.id,
                        storage_key=storage_key,
                        original_file_name=validated.original_file_name,
                        mime_type=validated.mime_type,
                        file_size=validated.file_size,
                        file_hash=validated.file_hash,
                        document_type=validated.document_type,
                    )
                )
                uow.audit_events.append(
                    quote_event(
                        document.id,
                        "QuoteFileStored",
                        aggregate_type="quote_document",
                        quote_id=str(quote.id),
                        file_hash=document.file_hash,
                        file_size=document.file_size,
                        uploaded_by_user_id=str(uploaded_by_user_id),
                    )
                )
                uow.commit()
                return _document_response(document)
            except Exception:
                uow.rollback()
                if storage_key:
                    with suppress(Exception):
                        self._file_storage.delete(storage_key)
                raise


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
        confidence_low_threshold: float = 0.70,
    ) -> None:
        self._uow_factory = uow_factory
        self._file_storage = file_storage
        self._document_extractor = MultiFormatQuoteDocumentExtractor(text_extractor)
        self._ai_service = ai_service
        self._prompt_registry = prompt_registry
        self._prompt_version = prompt_version
        self._model = model
        self._temperature = temperature
        self._normalizer = QuoteNormalizer()
        self._matcher = QuoteProductMatcher()
        self._compliance = TechnicalComplianceEvaluator()
        self._low_confidence = confidence_low_threshold

    @staticmethod
    def _status(value: object) -> EvidenceFindingStatus:
        try:
            return EvidenceFindingStatus(str(value or "found"))
        except ValueError as exc:
            raise QuoteExtractionFailure("AI quote field status is invalid.") from exc

    @staticmethod
    def _validate_missing_contract(raw: dict, statuses: dict, fields: tuple[str, ...]) -> None:
        for field in fields:
            status = statuses.get(field)
            if status == EvidenceFindingStatus.NOT_FOUND.value and raw.get(field) is not None:
                raise QuoteExtractionFailure(
                    f"AI quote response violates missing-value contract for {field}."
                )

    @staticmethod
    def _legacy_evidence(raw: object) -> list[dict]:
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, dict)]
        if isinstance(raw, dict):
            page = raw.get("page")
            return [
                {
                    "field": "item",
                    "locator": f"page:{page}",
                    "fragment": raw.get("fragment") or "",
                    "status": "found",
                    "confidence": raw.get("confidence") or 0,
                }
            ]
        return []

    def _create_evidence(
        self,
        uow,
        *,
        quote: Quote,
        document: QuoteDocument,
        run: QuoteExtractionRun,
        entity_type: str,
        entity_id: UUID,
        raw_evidence: list[dict],
        section_map: dict[str, object],
    ) -> list[QuoteEvidenceReference]:
        result: list[QuoteEvidenceReference] = []
        for raw in raw_evidence:
            locator = str(raw.get("locator") or "").strip()
            field_name = str(raw.get("field") or "item").strip()
            status = self._status(raw.get("status"))
            confidence = float(raw.get("confidence") or 0)
            fragment = " ".join(str(raw.get("fragment") or "").split())
            if status is EvidenceFindingStatus.NOT_FOUND:
                continue
            section = section_map.get(locator)
            if section is None:
                raise QuoteExtractionFailure("Quote evidence references an unknown source locator.")
            normalized_source = " ".join(section.text.split())
            if not fragment or fragment not in normalized_source:
                raise QuoteExtractionFailure("Quote evidence fragment is not grounded in its source document.")
            evidence = QuoteEvidenceReference(
                quote_id=quote.id,
                quote_document_id=document.id,
                extraction_run_id=run.id,
                entity_type=entity_type,
                entity_id=entity_id,
                field_name=field_name,
                locator_type=section.locator_type,
                locator=section.locator,
                fragment=fragment,
                extraction_method=section.extraction_method,
                finding_status=status,
                confidence=confidence,
            )
            result.append(uow.quotes.create_evidence(evidence))
        return result

    def execute(
        self,
        quote_id: UUID,
        task_record_id: UUID | None = None,
        *,
        force_reprocess: bool = False,
    ) -> UUID:
        prompt = self._prompt_registry.get("quote_extraction", self._prompt_version)
        schema_hash = _schema_hash(prompt.output_schema)
        with self._uow_factory() as uow:
            quote = uow.quotes.get_quote(quote_id, for_update=True)
            if quote is None:
                raise QuoteNotFound("Quote was not found.")
            documents = uow.quotes.list_documents(quote.id)
            if not documents:
                raise QuoteDocumentNotFound("Quote does not have a stored document.")
            document = documents[-1]
            fingerprint_data = "|".join(
                (
                    document.file_hash,
                    self._document_extractor.version,
                    self._model,
                    prompt.version,
                    prompt.schema_version,
                    schema_hash,
                )
            )
            fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()
            if not force_reprocess:
                completed = uow.quotes.get_completed_run_by_fingerprint(quote.id, fingerprint)
                if completed is not None and uow.quotes.list_items_by_run(completed.id):
                    return quote.id
            run_number = uow.quotes.next_run_number(quote.id)
            idempotency_key = fingerprint
            if force_reprocess or uow.quotes.get_run_by_key(quote.id, idempotency_key) is not None:
                idempotency_key = hashlib.sha256(
                    f"{fingerprint}|run:{run_number}".encode()
                ).hexdigest()
            run = uow.quotes.create_run(
                QuoteExtractionRun(
                    quote_id=quote.id,
                    quote_document_id=document.id,
                    tender_id=quote.tender_id,
                    supplier_id=quote.supplier_id,
                    idempotency_key=idempotency_key,
                    extraction_fingerprint=fingerprint,
                    run_number=run_number,
                    provider="openai",
                    extractor_name="multi-format-quote",
                    extractor_version=self._document_extractor.version,
                    prompt_version=prompt.version,
                    model=self._model,
                    schema_version=prompt.schema_version,
                    schema_hash=schema_hash,
                )
            )
            if quote.status is QuoteStatus.RECEIVED:
                quote.start_validation()
            if quote.status is QuoteStatus.VALIDATING:
                quote.start_extraction()
            elif quote.status is not QuoteStatus.EXTRACTING:
                raise InvalidQuoteState("Quote is not ready for extraction.")
            run.start()
            document.start_processing("multi-format-quote", self._document_extractor.version)
            uow.quotes.update_quote(quote)
            uow.quotes.update_run(run)
            uow.quotes.update_document(document)
            task = uow.quotes.get_task(task_record_id, for_update=True) if task_record_id else None
            if task is not None:
                task.start()
                uow.quotes.update_task(task)
            uow.audit_events.append(
                quote_event(
                    quote.id,
                    "QuoteAnalysisStarted",
                    extraction_run_id=str(run.id),
                    quote_document_id=str(document.id),
                    model=run.model,
                    prompt_version=run.prompt_version,
                    schema_version=run.schema_version,
                    extractor_version=run.extractor_version,
                    correlation_id=task.correlation_id if task else None,
                )
            )
            uow.audit_events.append(
                quote_event(
                    run.id,
                    "QuoteExtractionStarted",
                    aggregate_type="quote_extraction",
                    quote_id=str(quote.id),
                    model=run.model,
                    prompt_version=run.prompt_version,
                    schema_version=run.schema_version,
                    extractor_version=run.extractor_version,
                )
            )
            storage_key = document.storage_key
            document_type = document.document_type
            uow.commit()

        try:
            try:
                content = self._file_storage.read(storage_key)
            except DocumentStorageFailure as exc:
                raise QuoteStorageError("Quote document content is unavailable.") from exc
            extraction = self._document_extractor.extract(document_type, content)
            if not extraction.sections or not any(section.text.strip() for section in extraction.sections):
                raise QuoteExtractionFailure("Quote document does not contain extractable content.")
            pages = tuple(
                {
                    "page_number": section.page_number,
                    "locator_type": section.locator_type,
                    "locator": section.locator,
                    "text": section.text,
                }
                for section in extraction.sections
            )
            try:
                ai_result = self._ai_service.extract(
                    AIExtractionRequest(
                        prompt=prompt,
                        model=self._model,
                        temperature=self._temperature,
                        document_id=str(document.id),
                        pages=pages,
                    )
                )
            except AIExtractionFailure as exc:
                raise QuoteProviderError("Quote AI extraction provider is unavailable.") from exc
            raw_items = ai_result.payload.get("items")
            if not isinstance(raw_items, list) or not raw_items:
                raise QuoteExtractionFailure("AI quote response must contain at least one item.")
            raw_summary = ai_result.payload.get("summary") or {}
            if not isinstance(raw_summary, dict):
                raise QuoteExtractionFailure("AI quote summary must be an object.")
            self._validate_missing_contract(
                raw_summary,
                raw_summary.get("field_statuses") or {},
                ("currency", "subtotal", "tax", "total", "delivery_days", "valid_until", "commercial_terms"),
            )
            section_map = {section.locator: section for section in extraction.sections}
            with self._uow_factory() as uow:
                current = uow.quotes.get_quote(quote_id, for_update=True)
                current_run = uow.quotes.get_run(run.id, for_update=True)
                current_document = uow.quotes.get_document(document.id, for_update=True)
                current_task = uow.quotes.get_task(task_record_id, for_update=True) if task_record_id else None
                if current is None or current_run is None or current_document is None:
                    raise QuoteNotFound("Quote extraction state was not found.")
                snapshot = uow.catalogs.get_latest_snapshot(current.tender_id)
                if snapshot is None:
                    raise InvalidQuoteState("Quote normalization requires an approved catalog.")
                self._create_evidence(
                    uow,
                    quote=current,
                    document=current_document,
                    run=current_run,
                    entity_type="quote",
                    entity_id=current.id,
                    raw_evidence=self._legacy_evidence(raw_summary.get("evidence")),
                    section_map=section_map,
                )
                items: list[QuoteItem] = []
                for raw in raw_items:
                    if not isinstance(raw, dict):
                        raise QuoteExtractionFailure("AI quote item must be an object.")
                    name = str(raw.get("product_name") or "").strip()
                    if not name:
                        raise QuoteExtractionFailure("AI quote item is missing product_name.")
                    statuses = raw.get("field_statuses") or {}
                    self._validate_missing_contract(
                        raw,
                        statuses,
                        ("brand", "model", "quantity", "unit", "unit_price", "total_price", "currency", "delivery_days"),
                    )
                    quantity = self._normalizer.quantity(_decimal(raw.get("quantity")))
                    unit = self._normalizer.unit(raw.get("unit"))
                    currency = self._normalizer.currency(raw.get("currency"))
                    match = self._matcher.match(
                        snapshot.products,
                        name=name,
                        description=raw.get("description"),
                        brand=raw.get("brand"),
                        model=raw.get("model"),
                        unit=unit,
                        quantity=quantity,
                    )
                    requested_specs: dict[str, str] = {}
                    if match.product_id is not None:
                        matched_product = next(
                            (
                                product
                                for product in snapshot.products
                                if str(product.get("product_id")) == str(match.product_id)
                            ),
                            None,
                        )
                        if matched_product:
                            requested_specs = dict(matched_product.get("specifications") or {})
                    quoted_specs = {
                        str(key): str(value)
                        for key, value in (raw.get("quoted_specifications") or {}).items()
                    }
                    compliance, compliance_reason = self._compliance.evaluate(
                        requested_specs,
                        quoted_specs,
                    )
                    # Compatibility with Iteration 9's v1 payload only.
                    if not quoted_specs and isinstance(raw.get("technical_compliance"), bool):
                        compliance = (
                            ComplianceStatus.COMPLIANT
                            if raw["technical_compliance"]
                            else ComplianceStatus.NON_COMPLIANT
                        )
                    item_id = uuid4()
                    raw_evidence = self._legacy_evidence(raw.get("evidence"))
                    evidences = self._create_evidence(
                        uow,
                        quote=current,
                        document=current_document,
                        run=current_run,
                        entity_type="quote_item",
                        entity_id=item_id,
                        raw_evidence=raw_evidence,
                        section_map=section_map,
                    )
                    if not evidences:
                        raise QuoteExtractionFailure("Every quote item requires grounded evidence.")
                    primary = next(
                        (item for item in evidences if item.field_name in {"unit_price", "total_price", "item"}),
                        evidences[0],
                    )
                    source_page = None
                    if primary.locator.startswith("page:"):
                        try:
                            source_page = int(primary.locator.split(":", 1)[1])
                        except ValueError:
                            source_page = None
                    confidence = min((item.confidence for item in evidences), default=0.0)
                    item = QuoteItem(
                        id=item_id,
                        quote_id=current.id,
                        extraction_run_id=current_run.id,
                        catalog_product_id=match.product_id,
                        product_name=name,
                        description=raw.get("description"),
                        brand=raw.get("brand"),
                        model=raw.get("model"),
                        quantity=quantity,
                        unit=unit,
                        unit_price=_decimal(raw.get("unit_price")),
                        total_price=_decimal(raw.get("total_price")),
                        currency=currency,
                        delivery_days=(int(raw["delivery_days"]) if raw.get("delivery_days") is not None else None),
                        technical_compliance=None,
                        compliance_status=compliance,
                        quoted_specifications=quoted_specs,
                        match_status=match.status,
                        match_score=match.score,
                        match_reason=f"{match.reason} Technical evaluation: {compliance_reason}",
                        notes=raw.get("notes"),
                        source_evidence_id=primary.id,
                        source_page=source_page,
                        evidence_fragment=primary.fragment,
                        confidence=confidence,
                        original_extracted=dict(raw),
                    )
                    item.recalculate_warnings(low_confidence_threshold=self._low_confidence)
                    items.append(item)
                uow.quotes.supersede_current_items(current.id)
                uow.quotes.create_items(current.id, tuple(items))
                current.mark_extracted()
                current.apply_summary(
                    currency=self._normalizer.currency(raw_summary.get("currency")),
                    subtotal_amount=_decimal(raw_summary.get("subtotal")),
                    tax_amount=_decimal(raw_summary.get("tax")),
                    total_amount=_decimal(raw_summary.get("total")),
                    delivery_time_days=(int(raw_summary["delivery_days"]) if raw_summary.get("delivery_days") is not None else None),
                    commercial_terms=raw_summary.get("commercial_terms"),
                    valid_until=_parse_datetime(raw_summary.get("valid_until")),
                )
                current.start_review()
                current.last_error = None
                current_document.extractor_name = extraction.extractor_name
                current_document.extractor_version = extraction.extractor_version
                current_document.complete()
                current_run.extractor_name = extraction.extractor_name
                current_run.extractor_version = extraction.extractor_version
                current_run.complete(
                    provider_response_id=ai_result.provider_response_id,
                    input_tokens=ai_result.input_tokens,
                    output_tokens=ai_result.output_tokens,
                    estimated_cost_usd=ai_result.estimated_cost_usd,
                    raw_response=ai_result.payload,
                    duration_ms=extraction.duration_ms + ai_result.duration_ms,
                )
                uow.quotes.update_quote(current)
                uow.quotes.update_document(current_document)
                uow.quotes.update_run(current_run)
                if current_task is not None:
                    current_task.succeed()
                    uow.quotes.update_task(current_task)
                metadata = {
                    "tender_id": str(current.tender_id),
                    "supplier_id": str(current.supplier_id),
                    "extraction_run_id": str(current_run.id),
                    "quote_document_id": str(current_document.id),
                    "item_count": len(items),
                    "input_tokens": ai_result.input_tokens,
                    "output_tokens": ai_result.output_tokens,
                    "estimated_cost_usd": str(ai_result.estimated_cost_usd),
                    "model": ai_result.model,
                    "prompt_version": current_run.prompt_version,
                    "schema_version": current_run.schema_version,
                    "extractor_version": current_run.extractor_version,
                }
                uow.audit_events.append(quote_event(current.id, "QuoteAnalyzed", **metadata))
                uow.audit_events.append(quote_event(current.id, "QuoteNormalized", **metadata))
                # Compatibility with Iteration 9 audit expectations.
                uow.audit_events.append(quote_event(current.id, "QuoteExtractedAndNormalized", **metadata))
                uow.commit()
                return current.id
        except Exception as exc:
            with self._uow_factory() as uow:
                current = uow.quotes.get_quote(quote_id, for_update=True)
                failed_run = uow.quotes.get_run(run.id, for_update=True)
                failed_document = uow.quotes.get_document(document.id, for_update=True)
                failed_task = uow.quotes.get_task(task_record_id, for_update=True) if task_record_id else None
                if current is not None:
                    try:
                        current.mark_failed(exc)
                    except InvalidQuoteState:
                        current.record_error(exc)
                    uow.quotes.update_quote(current)
                if failed_run is not None:
                    failed_run.fail(exc)
                    uow.quotes.update_run(failed_run)
                if failed_document is not None:
                    failed_document.fail(exc)
                    uow.quotes.update_document(failed_document)
                retryable = isinstance(exc, (RetryableQuoteExtractionFailure, QuoteStorageError, QuoteProviderError))
                if failed_task is not None:
                    failed_task.fail(exc, retryable=retryable)
                    uow.quotes.update_task(failed_task)
                uow.audit_events.append(
                    quote_event(
                        quote_id,
                        "QuoteAnalysisFailed",
                        extraction_run_id=str(run.id),
                        error_type=type(exc).__name__,
                        retryable=retryable,
                    )
                )
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


class GetQuoteDocuments:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, quote_id: UUID) -> tuple[QuoteDocumentResponse, ...]:
        with self._uow_factory() as uow:
            if uow.quotes.get_quote(quote_id) is None:
                raise QuoteNotFound("Quote was not found.")
            return tuple(_document_response(item) for item in uow.quotes.list_documents(quote_id))


class GetQuoteEvidence:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, quote_id: UUID) -> tuple[QuoteEvidenceResponse, ...]:
        with self._uow_factory() as uow:
            if uow.quotes.get_quote(quote_id) is None:
                raise QuoteNotFound("Quote was not found.")
            return tuple(
                QuoteEvidenceResponse(
                    id=item.id,
                    quote_document_id=item.quote_document_id,
                    extraction_run_id=item.extraction_run_id,
                    entity_type=item.entity_type,
                    entity_id=item.entity_id,
                    field_name=item.field_name,
                    locator_type=item.locator_type,
                    locator=item.locator,
                    fragment=item.fragment,
                    extraction_method=item.extraction_method,
                    finding_status=item.finding_status.value,
                    confidence=item.confidence,
                    created_at=item.created_at,
                )
                for item in uow.quotes.list_evidence(quote_id)
            )


class GetQuoteProcessingStatus:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, quote_id: UUID) -> QuoteProcessingStatusResponse:
        with self._uow_factory() as uow:
            quote = uow.quotes.get_quote(quote_id)
            if quote is None:
                raise QuoteNotFound("Quote was not found.")
            task = uow.quotes.get_latest_task(quote_id)
            runs = uow.quotes.list_runs(quote_id)
            run = runs[-1] if runs else None
            return QuoteProcessingStatusResponse(
                quote_id=quote.id,
                quote_status=quote.status,
                task_id=task.id if task else None,
                task_status=task.status if task else None,
                correlation_id=task.correlation_id if task else None,
                attempt_count=task.attempt_count if task else 0,
                extraction_run_id=run.id if run else None,
                extraction_status=run.status if run else None,
                last_error=quote.last_error or (task.last_error if task else None),
            )


class UpdateQuoteItem:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, quote_id: UUID, item_id: UUID, command: UpdateQuoteItemCommand) -> QuoteItemResponse:
        with self._uow_factory() as uow:
            quote = uow.quotes.get_quote(quote_id, for_update=True)
            item = uow.quotes.get_item(item_id, for_update=True)
            if quote is None:
                raise QuoteNotFound("Quote was not found.")
            if item is None or item.quote_id != quote.id or not item.is_current:
                raise QuoteItemNotFound("Quote item was not found in the current extraction.")
            if quote.status is not QuoteStatus.PENDING_REVIEW:
                raise InvalidQuoteState("Quote items can only be corrected during human review.")
            if not uow.users.exists(command.changed_by_user_id):
                raise InvalidQuoteState("Quote reviewer user does not exist.")
            catalog_product_id = command.catalog_product_id
            if catalog_product_id is not None:
                product = uow.catalogs.get_product(catalog_product_id)
                if product is None or product.tender_id != quote.tender_id:
                    raise InvalidQuoteState("Selected requested product does not belong to this tender.")
                if product.status is not ProductStatus.APPROVED:
                    raise InvalidQuoteState("Rejected or unapproved products cannot be comparable.")
            before = item.snapshot()
            item.apply_human_review(
                catalog_product_id=catalog_product_id if command.catalog_product_id is not None else item.catalog_product_id,
                product_name=command.product_name,
                description=command.description,
                brand=command.brand,
                model=command.model,
                quantity=command.quantity,
                unit=command.unit,
                unit_price=command.unit_price,
                total_price=command.total_price,
                currency=command.currency,
                delivery_days=command.delivery_days,
                compliance_status=command.compliance_status,
                notes=command.notes,
            )
            if command.catalog_product_id is not None:
                item.match_status = ProductMatchStatus.MATCHED
                item.match_score = 1.0
                item.match_reason = "Requested product association confirmed by human reviewer."
            item.recalculate_warnings()
            after = item.snapshot()
            changed_fields = tuple(key for key in before if before[key] != after[key])
            if changed_fields:
                uow.quotes.update_item(item)
                quote.record_manual_edit()
                uow.quotes.update_quote(quote)
                uow.quotes.add_item_revision(
                    QuoteItemRevision(
                        quote_id=quote.id,
                        quote_item_id=item.id,
                        changed_by_user_id=command.changed_by_user_id,
                        before=before,
                        after=after,
                        changed_fields=changed_fields,
                    )
                )
                uow.audit_events.append(
                    quote_event(
                        quote.id,
                        "QuoteItemCorrected",
                        quote_item_id=str(item.id),
                        changed_by_user_id=str(command.changed_by_user_id),
                        changed_fields=list(changed_fields),
                    )
                )
                uow.commit()
            return _item_response(item)


class SubmitQuoteForReview:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, quote_id: UUID, reviewer_user_id: UUID) -> QuoteResponse:
        with self._uow_factory() as uow:
            quote = uow.quotes.get_quote(quote_id, for_update=True)
            if quote is None:
                raise QuoteNotFound("Quote was not found.")
            if not uow.users.exists(reviewer_user_id):
                raise InvalidQuoteState("Quote reviewer user does not exist.")
            if quote.status is QuoteStatus.NORMALIZED:
                quote.start_review()
                uow.quotes.update_quote(quote)
            elif quote.status is not QuoteStatus.PENDING_REVIEW:
                raise InvalidQuoteState("Only normalized quotes can be submitted for review.")
            uow.audit_events.append(
                quote_event(
                    quote.id,
                    "QuoteSubmittedForReview",
                    reviewer_user_id=str(reviewer_user_id),
                )
            )
            uow.commit()
            return _quote_response(uow, quote)


class ApproveQuote:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, quote_id: UUID, reviewer_user_id: UUID) -> QuoteResponse:
        with self._uow_factory() as uow:
            quote = uow.quotes.get_quote(quote_id, for_update=True)
            if quote is None:
                raise QuoteNotFound("Quote was not found.")
            if not uow.users.exists(reviewer_user_id):
                raise InvalidQuoteState("Quote reviewer user does not exist.")
            if quote.status is not QuoteStatus.PENDING_REVIEW:
                raise InvalidQuoteState("Only pending-review quotes can be approved.")
            items = uow.quotes.list_items(quote.id)
            if not items:
                raise InvalidQuoteState("Incomplete quotes without items cannot be approved.")
            for item in items:
                if item.catalog_product_id is None or item.match_status is not ProductMatchStatus.MATCHED:
                    raise InvalidQuoteState("Every quote item must have a human-resolved requested product match before approval.")
                if item.quantity is None:
                    raise InvalidQuoteState("Every quote item requires a reviewed quantity before approval.")
                if item.unit_price is None and item.total_price is None:
                    raise InvalidQuoteState("Every quote item requires a reviewed price before approval.")
                if item.currency is None:
                    raise InvalidQuoteState("Every priced quote item requires an explicit currency before approval.")
            run_id = items[0].extraction_run_id
            if run_id is not None:
                run = uow.quotes.get_run(run_id, for_update=True)
                if run is not None:
                    run.mark_approved_source()
                    uow.quotes.update_run(run)
            quote.approve(reviewer_user_id, run_id)
            quote = uow.quotes.update_quote(quote)
            uow.audit_events.append(
                quote_event(
                    quote.id,
                    "QuoteApproved",
                    tender_id=str(quote.tender_id),
                    supplier_id=str(quote.supplier_id),
                    reviewer_user_id=str(reviewer_user_id),
                    extraction_run_id=str(run_id) if run_id else None,
                    warnings=sorted({warning for item in items for warning in item.warnings}),
                )
            )
            uow.commit()
            return _quote_response(uow, quote)


class RejectQuote:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, quote_id: UUID, reviewer_user_id: UUID, reason: str) -> QuoteResponse:
        with self._uow_factory() as uow:
            quote = uow.quotes.get_quote(quote_id, for_update=True)
            if quote is None:
                raise QuoteNotFound("Quote was not found.")
            if not uow.users.exists(reviewer_user_id):
                raise InvalidQuoteState("Quote reviewer user does not exist.")
            quote.reject(reviewer_user_id, reason)
            quote = uow.quotes.update_quote(quote)
            uow.audit_events.append(
                quote_event(
                    quote.id,
                    "QuoteRejected",
                    reviewer_user_id=str(reviewer_user_id),
                    reason=quote.rejection_reason,
                )
            )
            uow.commit()
            return _quote_response(uow, quote)


class ReprocessQuote:
    def __init__(self, uow_factory: UnitOfWorkFactory, queue: QuoteAnalysisQueue) -> None:
        self._uow_factory = uow_factory
        self._queue = queue

    def execute(self, quote_id: UUID, requested_by_user_id: UUID) -> QuoteProcessingStatusResponse:
        with self._uow_factory() as uow:
            quote = uow.quotes.get_quote(quote_id)
            if quote is None:
                raise QuoteNotFound("Quote was not found.")
            if not uow.users.exists(requested_by_user_id):
                raise InvalidQuoteState("Quote reprocess user does not exist.")
        QueueQuoteProcessing(self._uow_factory, self._queue).execute(
            quote_id,
            force_reprocess=True,
        )
        return GetQuoteProcessingStatus(self._uow_factory).execute(quote_id)


class ReviewQuote:
    """Compatibility facade for Iteration 9's combined review endpoint."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, quote_id: UUID, command: QuoteReviewCommand) -> QuoteResponse:
        if command.action == "approve":
            return ApproveQuote(self._uow_factory).execute(quote_id, command.reviewer_user_id)
        if command.action == "reject":
            return RejectQuote(self._uow_factory).execute(
                quote_id,
                command.reviewer_user_id,
                command.rejection_reason or "",
            )
        raise InvalidQuoteState("Unsupported quote review action.")


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
                f"{item.id}:{item.version}:{item.file_hash}:{item.approved_extraction_run_id}"
                for item in sorted(quotes, key=lambda value: str(value.id))
            ]
            approved_quotes_version = hashlib.sha256("|".join(version_payload).encode()).hexdigest()
            key = hashlib.sha256(
                "|".join(
                    (
                        str(tender_id),
                        str(snapshot.id),
                        str(snapshot.version),
                        approved_quotes_version,
                        self._scoring_config_version,
                    )
                ).encode()
            ).hexdigest()
            existing = uow.quotes.get_comparison_by_key(tender_id, key)
            if existing is not None:
                return _comparison_response(existing)
            entries: list[tuple[str, str, QuoteItem]] = []
            for quote in quotes:
                supplier = uow.suppliers.get_supplier(quote.supplier_id)
                if supplier is None:
                    raise SupplierNotFound("Quote supplier was not found.")
                supplier_name = supplier.trade_name or supplier.legal_name or supplier.normalized_domain or str(supplier.id)
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
