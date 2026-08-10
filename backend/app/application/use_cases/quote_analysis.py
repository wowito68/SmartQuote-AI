import hashlib
import urllib.error
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.application.dtos.quote_analysis import (
    ExtractionArtifactResponse,
    QuoteAnalysisResponse,
)
from app.application.dtos.quotes import QuoteProcessingStatusResponse
from app.application.ports.ai_extraction_service import AIExtractionRequest
from app.application.ports.quote_analysis_queue import QuoteAnalysisQueue
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.application.use_cases.quotes import (
    GetQuoteEvidence,
    GetQuoteProcessingStatus,
    ProcessSupplierQuote,
    _decimal,
    _item_response,
    _parse_datetime,
    _run_response,
    _schema_hash,
)
from app.domain.catalog.exceptions import AIExtractionFailure, AIResponseValidationError
from app.domain.quotes.analysis import (
    apply_analysis_summary,
    mark_analysis_failed,
    mark_analyzed,
    mark_pending_review,
    mark_ready_for_analysis,
    restart_analysis,
    start_analysis,
)
from app.domain.quotes.artifacts import ExtractionArtifact
from app.domain.quotes.entities import QuoteExtractionRun, QuoteItem, QuoteTaskRecord
from app.domain.quotes.events import quote_event
from app.domain.quotes.exceptions import (
    InvalidQuoteState,
    QuoteDocumentNotFound,
    QuoteExtractionFailure,
    QuoteNotFound,
    QuoteProviderError,
    QuoteStorageError,
    RetryableQuoteExtractionFailure,
)
from app.domain.quotes.value_objects import (
    ComplianceStatus,
    ProductMatchStatus,
    QuoteExtractionRunStatus,
    QuoteStatus,
    QuoteTaskStatus,
    QuoteWarning,
)
from app.domain.shared.exceptions import ValidationError


def _provider_error_is_retryable(error: BaseException) -> bool:
    current: BaseException | None = error
    while current is not None:
        if isinstance(current, urllib.error.HTTPError):
            return current.code in {408, 425, 429} or 500 <= current.code <= 599
        if isinstance(current, (urllib.error.URLError, TimeoutError, ConnectionError)):
            return True
        current = current.__cause__
    # The legacy AI port historically used AIExtractionFailure for provider outages.
    # Structural response failures have their own AIResponseValidationError type.
    return not isinstance(error, AIResponseValidationError)


def _artifact_response(artifact: ExtractionArtifact) -> ExtractionArtifactResponse:
    return ExtractionArtifactResponse(
        id=artifact.id,
        extraction_run_id=artifact.extraction_run_id,
        schema_version=artifact.schema_version,
        structured_output=dict(artifact.structured_output),
        created_at=artifact.created_at,
    )


class QueueQuoteAnalysis:
    """Validate an explicit analysis request and publish the existing Celery task."""

    def __init__(self, uow_factory: UnitOfWorkFactory, queue: QuoteAnalysisQueue) -> None:
        self._uow_factory = uow_factory
        self._queue = queue

    def execute(
        self,
        quote_id: UUID,
        requested_by_user_id: UUID,
        *,
        force_reanalysis: bool = False,
        correlation_id: str | None = None,
    ) -> QuoteProcessingStatusResponse:
        correlation = correlation_id or f"quote-analysis:{quote_id}:{uuid4().hex}"
        with self._uow_factory() as uow:
            quote = uow.quotes.get_quote(quote_id, for_update=True)
            if quote is None:
                raise QuoteNotFound("Quote was not found.")
            if not uow.users.exists(requested_by_user_id):
                raise InvalidQuoteState("Quote analysis user does not exist.")
            documents = uow.quotes.list_documents(quote.id)
            if not documents:
                raise QuoteDocumentNotFound("Quote does not have a stored document.")
            existing_task = uow.quotes.get_task_by_correlation(correlation)
            if existing_task is not None:
                return GetQuoteProcessingStatus(self._uow_factory).execute(quote.id)

            if not force_reanalysis:
                completed = [
                    run
                    for run in uow.quotes.list_runs(quote.id)
                    if run.status
                    in {QuoteExtractionRunStatus.COMPLETED, QuoteExtractionRunStatus.REUSED}
                ]
                if completed:
                    latest = completed[-1]
                    artifact = uow.quote_artifacts.get_by_run(latest.id)
                    if artifact is not None and uow.quotes.list_items_by_run(latest.id):
                        task = uow.quotes.get_latest_task(quote.id)
                        if task is None:
                            task = QuoteTaskRecord(
                                quote_id=quote.id,
                                correlation_id=correlation,
                            )
                            task.start()
                            task.succeed()
                            uow.quotes.create_task(task)
                            uow.commit()
                        return GetQuoteProcessingStatus(self._uow_factory).execute(
                            quote.id
                        )

            if force_reanalysis:
                restart_analysis(quote)
                uow.audit_events.append(
                    quote_event(
                        quote.id,
                        "quote.reanalysis_requested",
                        requested_by_user_id=str(requested_by_user_id),
                        correlation_id=correlation,
                    )
                )
                uow.audit_events.append(
                    quote_event(
                        quote.id,
                        "QuoteReprocessed",
                        requested_by_user_id=str(requested_by_user_id),
                        correlation_id=correlation,
                    )
                )
            elif quote.status in {QuoteStatus.RECEIVED, QuoteStatus.VALIDATING}:
                mark_ready_for_analysis(quote)
            elif quote.status is not QuoteStatus.READY_FOR_ANALYSIS:
                raise InvalidQuoteState(
                    "Quote must be ready_for_analysis before analysis can start."
                )

            task = QuoteTaskRecord(
                quote_id=quote.id,
                correlation_id=correlation,
                force_reprocess=force_reanalysis,
            )
            uow.quotes.create_task(task)
            uow.quotes.update_quote(quote)
            uow.commit()

        try:
            self._queue.enqueue(
                quote_id,
                correlation,
                task_record_id=task.id,
                force_reprocess=force_reanalysis,
            )
        except TypeError:
            # Compatibility with older queue test doubles.
            self._queue.enqueue(quote_id, correlation)
        except Exception as exc:
            with self._uow_factory() as uow:
                current = uow.quotes.get_quote(quote_id, for_update=True)
                current_task = uow.quotes.get_task(task.id, for_update=True)
                if current is not None:
                    mark_analysis_failed(current, exc)
                    uow.quotes.update_quote(current)
                if current_task is not None:
                    current_task.fail(exc, retryable=True)
                    uow.quotes.update_task(current_task)
                uow.audit_events.append(
                    quote_event(
                        quote_id,
                        "quote.analysis_failed",
                        error_type=type(exc).__name__,
                        retryable=True,
                        correlation_id=correlation,
                    )
                )
                uow.commit()
            raise RetryableQuoteExtractionFailure(
                "Unable to queue quote analysis."
            ) from exc
        return GetQuoteProcessingStatus(self._uow_factory).execute(quote_id)


class AnalyzeQuote(ProcessSupplierQuote):
    """Analyze an existing quote through the provider-neutral AI extraction port."""

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
                completed = uow.quotes.get_completed_run_by_fingerprint(
                    quote.id,
                    fingerprint,
                )
                if completed is not None:
                    artifact = uow.quote_artifacts.get_by_run(completed.id)
                    if artifact is not None and uow.quotes.list_items_by_run(completed.id):
                        return quote.id

            run_number = uow.quotes.next_run_number(quote.id)
            idempotency_key = fingerprint
            if force_reprocess or uow.quotes.get_run_by_key(
                quote.id,
                idempotency_key,
            ) is not None:
                idempotency_key = hashlib.sha256(
                    f"{fingerprint}|run:{run_number}".encode()
                ).hexdigest()
            run = QuoteExtractionRun(
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
            uow.quotes.create_run(run)
            if force_reprocess and quote.status is not QuoteStatus.READY_FOR_ANALYSIS:
                restart_analysis(quote)
            if quote.status in {QuoteStatus.RECEIVED, QuoteStatus.VALIDATING}:
                mark_ready_for_analysis(quote)
            start_analysis(quote)
            run.start()
            document.start_processing(
                "multi-format-quote",
                self._document_extractor.version,
            )
            task = (
                uow.quotes.get_task(task_record_id, for_update=True)
                if task_record_id
                else None
            )
            if task is not None:
                task.start()
                uow.quotes.update_task(task)
            uow.quotes.update_quote(quote)
            uow.quotes.update_run(run)
            uow.quotes.update_document(document)
            metadata = {
                "extraction_run_id": str(run.id),
                "quote_document_id": str(document.id),
                "model": run.model,
                "prompt_version": run.prompt_version,
                "schema_version": run.schema_version,
                "input_hash": fingerprint,
                "correlation_id": task.correlation_id if task else None,
            }
            uow.audit_events.append(
                quote_event(quote.id, "quote.analysis_started", **metadata)
            )
            uow.audit_events.append(
                quote_event(quote.id, "QuoteAnalysisStarted", **metadata)
            )
            storage_key = document.storage_key
            document_type = document.document_type
            uow.commit()

        try:
            try:
                content = self._file_storage.read(storage_key)
            except Exception as exc:
                raise QuoteStorageError(
                    "Quote document content is unavailable."
                ) from exc
            extraction = self._document_extractor.extract(document_type, content)
            if not extraction.sections or not any(
                section.text.strip() for section in extraction.sections
            ):
                raise QuoteExtractionFailure(
                    "Quote document does not contain extractable content."
                )
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
            except AIResponseValidationError as exc:
                raise QuoteExtractionFailure(
                    "Quote AI response failed structural validation."
                ) from exc
            except AIExtractionFailure as exc:
                if _provider_error_is_retryable(exc):
                    raise QuoteProviderError(
                        "Quote AI provider is temporarily unavailable."
                    ) from exc
                raise QuoteExtractionFailure(
                    "Quote AI provider permanently rejected the request."
                ) from exc

            raw_items = ai_result.payload.get("items")
            if not isinstance(raw_items, list) or not raw_items:
                raise QuoteExtractionFailure(
                    "AI quote response must contain at least one item."
                )
            raw_summary = ai_result.payload.get("summary") or {}
            if not isinstance(raw_summary, dict):
                raise QuoteExtractionFailure("AI quote summary must be an object.")
            self._validate_missing_contract(
                raw_summary,
                raw_summary.get("field_statuses") or {},
                (
                    "currency",
                    "subtotal",
                    "tax",
                    "total",
                    "delivery_days",
                    "valid_until",
                    "commercial_terms",
                ),
            )
            section_map = {section.locator: section for section in extraction.sections}

            with self._uow_factory() as uow:
                current = uow.quotes.get_quote(quote_id, for_update=True)
                current_run = uow.quotes.get_run(run.id, for_update=True)
                current_document = uow.quotes.get_document(
                    document.id,
                    for_update=True,
                )
                current_task = (
                    uow.quotes.get_task(task_record_id, for_update=True)
                    if task_record_id
                    else None
                )
                if current is None or current_run is None or current_document is None:
                    raise QuoteNotFound("Quote analysis state was not found.")
                snapshot = uow.catalogs.get_latest_snapshot(current.tender_id)
                if snapshot is None:
                    raise InvalidQuoteState(
                        "Quote analysis requires an approved tender catalog."
                    )

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
                        raise QuoteExtractionFailure(
                            "AI quote item is missing product_name."
                        )
                    statuses = raw.get("field_statuses") or {}
                    self._validate_missing_contract(
                        raw,
                        statuses,
                        (
                            "brand",
                            "model",
                            "quantity",
                            "unit",
                            "unit_price",
                            "total_price",
                            "currency",
                            "delivery_days",
                        ),
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
                                if str(product.get("product_id"))
                                == str(match.product_id)
                            ),
                            None,
                        )
                        if matched_product:
                            requested_specs = dict(
                                matched_product.get("specifications") or {}
                            )
                    quoted_specs = {
                        str(key): str(value)
                        for key, value in (
                            raw.get("quoted_specifications") or {}
                        ).items()
                    }
                    compliance, compliance_reason = self._compliance.evaluate(
                        requested_specs,
                        quoted_specs,
                    )
                    if not quoted_specs and isinstance(
                        raw.get("technical_compliance"),
                        bool,
                    ):
                        compliance = (
                            ComplianceStatus.COMPLIANT
                            if raw["technical_compliance"]
                            else ComplianceStatus.NON_COMPLIANT
                        )
                    item_id = uuid4()
                    evidences = self._create_evidence(
                        uow,
                        quote=current,
                        document=current_document,
                        run=current_run,
                        entity_type="quote_item",
                        entity_id=item_id,
                        raw_evidence=self._legacy_evidence(raw.get("evidence")),
                        section_map=section_map,
                    )
                    primary = next(
                        (
                            evidence
                            for evidence in evidences
                            if evidence.field_name
                            in {"unit_price", "total_price", "item"}
                        ),
                        evidences[0] if evidences else None,
                    )
                    source_page = None
                    if primary is not None and primary.locator.startswith("page:"):
                        try:
                            source_page = int(primary.locator.split(":", 1)[1])
                        except ValueError:
                            source_page = None
                    confidence = min(
                        (evidence.confidence for evidence in evidences),
                        default=0.0,
                    )
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
                        delivery_days=(
                            int(raw["delivery_days"])
                            if raw.get("delivery_days") is not None
                            else None
                        ),
                        technical_compliance=None,
                        compliance_status=compliance,
                        quoted_specifications=quoted_specs,
                        match_status=match.status,
                        match_score=match.score,
                        match_reason=(
                            f"{match.reason} Technical evaluation: "
                            f"{compliance_reason}"
                        ),
                        notes=raw.get("notes"),
                        source_evidence_id=primary.id if primary else None,
                        source_page=source_page,
                        evidence_fragment=primary.fragment if primary else None,
                        confidence=confidence,
                        original_extracted=dict(raw),
                    )
                    item.recalculate_warnings(
                        low_confidence_threshold=self._low_confidence
                    )
                    if not evidences:
                        item.warnings = tuple(
                            dict.fromkeys(
                                (*item.warnings, QuoteWarning.EVIDENCE_MISSING.value)
                            )
                        )
                    items.append(item)

                uow.quotes.supersede_current_items(current.id)
                persisted_items = uow.quotes.create_items(current.id, tuple(items))
                uow.quote_artifacts.create(
                    ExtractionArtifact(
                        extraction_run_id=current_run.id,
                        schema_version=current_run.schema_version,
                        structured_output=ai_result.payload,
                    )
                )
                apply_analysis_summary(
                    current,
                    currency=self._normalizer.currency(raw_summary.get("currency")),
                    subtotal_amount=_decimal(raw_summary.get("subtotal")),
                    tax_amount=_decimal(raw_summary.get("tax")),
                    total_amount=_decimal(raw_summary.get("total")),
                    delivery_time_days=(
                        int(raw_summary["delivery_days"])
                        if raw_summary.get("delivery_days") is not None
                        else None
                    ),
                    commercial_terms=raw_summary.get("commercial_terms"),
                    valid_until=_parse_datetime(raw_summary.get("valid_until")),
                )
                mark_analyzed(current)
                mark_pending_review(current)
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
                common = {
                    "extraction_run_id": str(current_run.id),
                    "quote_document_id": str(current_document.id),
                    "item_count": len(persisted_items),
                    "input_tokens": ai_result.input_tokens,
                    "output_tokens": ai_result.output_tokens,
                    "estimated_cost_usd": str(ai_result.estimated_cost_usd),
                    "model": ai_result.model,
                    "prompt_version": current_run.prompt_version,
                    "schema_version": current_run.schema_version,
                    "input_hash": current_run.extraction_fingerprint,
                }
                for item in persisted_items:
                    uow.audit_events.append(
                        quote_event(
                            item.id,
                            "quote.item_extracted",
                            aggregate_type="quote_item",
                            quote_id=str(current.id),
                            extraction_run_id=str(current_run.id),
                            confidence=item.confidence,
                            product_id=(
                                str(item.catalog_product_id)
                                if item.catalog_product_id
                                else None
                            ),
                        )
                    )
                    if (
                        item.warnings
                        or item.match_status is not ProductMatchStatus.MATCHED
                        or item.confidence < self._low_confidence
                    ):
                        uow.audit_events.append(
                            quote_event(
                                item.id,
                                "quote.item_flagged_for_review",
                                aggregate_type="quote_item",
                                quote_id=str(current.id),
                                warnings=list(item.warnings),
                                match_status=item.match_status.value,
                                confidence=item.confidence,
                            )
                        )
                uow.audit_events.append(
                    quote_event(current.id, "quote.analysis_completed", **common)
                )
                uow.audit_events.append(
                    quote_event(current.id, "QuoteAnalyzed", **common)
                )
                uow.commit()
                return current.id
        except Exception as exc:
            with self._uow_factory() as uow:
                current = uow.quotes.get_quote(quote_id, for_update=True)
                failed_run = uow.quotes.get_run(run.id, for_update=True)
                failed_document = uow.quotes.get_document(
                    document.id,
                    for_update=True,
                )
                failed_task = (
                    uow.quotes.get_task(task_record_id, for_update=True)
                    if task_record_id
                    else None
                )
                if current is not None:
                    mark_analysis_failed(current, exc)
                    uow.quotes.update_quote(current)
                if failed_run is not None:
                    failed_run.fail(exc)
                    uow.quotes.update_run(failed_run)
                if failed_document is not None:
                    failed_document.fail(exc)
                    uow.quotes.update_document(failed_document)
                retryable = isinstance(
                    exc,
                    (RetryableQuoteExtractionFailure, QuoteStorageError, QuoteProviderError),
                )
                if failed_task is not None:
                    failed_task.fail(exc, retryable=retryable)
                    uow.quotes.update_task(failed_task)
                uow.audit_events.append(
                    quote_event(
                        quote_id,
                        "quote.analysis_failed",
                        extraction_run_id=str(run.id),
                        error_type=type(exc).__name__,
                        retryable=retryable,
                    )
                )
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
            if isinstance(exc, QuoteExtractionFailure):
                raise
            if isinstance(exc, ValidationError):
                raise QuoteExtractionFailure(str(exc)) from exc
            raise QuoteExtractionFailure(str(exc)) from exc


class GetQuoteAnalysis:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        *,
        confidence_review_threshold: float = 0.70,
    ) -> None:
        self._uow_factory = uow_factory
        self._confidence_review_threshold = confidence_review_threshold

    def execute(self, quote_id: UUID) -> QuoteAnalysisResponse:
        processing = GetQuoteProcessingStatus(self._uow_factory).execute(quote_id)
        evidence = GetQuoteEvidence(self._uow_factory).execute(quote_id)
        with self._uow_factory() as uow:
            quote = uow.quotes.get_quote(quote_id)
            if quote is None:
                raise QuoteNotFound("Quote was not found.")
            runs = uow.quotes.list_runs(quote_id)
            latest_run = runs[-1] if runs else None
            artifact = (
                uow.quote_artifacts.get_by_run(latest_run.id)
                if latest_run is not None
                else None
            )
            items = tuple(_item_response(item) for item in uow.quotes.list_items(quote_id))
            requires_review = quote.status is QuoteStatus.PENDING_REVIEW or any(
                item.warnings
                or item.catalog_product_id is None
                or item.match_status is not ProductMatchStatus.MATCHED
                or item.confidence < self._confidence_review_threshold
                or item.source_evidence_id is None
                for item in items
            )
            return QuoteAnalysisResponse(
                quote_id=quote.id,
                quote_status=quote.status,
                processing=processing,
                latest_run=_run_response(latest_run) if latest_run else None,
                artifact=_artifact_response(artifact) if artifact else None,
                items=items,
                evidence=evidence,
                requires_review=requires_review,
                last_error=quote.last_error,
            )
