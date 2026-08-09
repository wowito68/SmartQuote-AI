import hashlib
import json
import uuid
from contextlib import suppress
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from app.application.dtos.quote_reception import (
    AddQuoteDocumentCommand, EvidenceResponse, ProcessingStatusResponse, QuoteDetailResponse,
    QuoteDocumentResponse, QuoteItemReviewResponse, ReceiveQuoteCommand, UpdateQuoteItemCommand,
)
from app.application.exceptions import TenderNotFound
from app.application.ports.ai_extraction_service import AIExtractionRequest, AIExtractionService
from app.application.ports.file_storage import FileStorage
from app.application.ports.prompt_registry import PromptRegistry
from app.application.ports.quote_analysis_queue import QuoteAnalysisQueue
from app.application.ports.quote_document_extractor import QuoteDocumentExtractor
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.application.services.quote_analysis import (
    QuoteProductMatcher, TechnicalComplianceEvaluator, price_warnings,
)
from app.application.services.quote_document_validation import QuoteDocumentValidator
from app.domain.catalog.value_objects import ProductStatus
from app.domain.quotes.entities import (
    Quote, QuoteDocument, QuoteEvidenceReference, QuoteExtractionRun, QuoteItem,
    QuoteItemRevision, QuoteTaskRecord,
)
from app.domain.quotes.events import quote_event
from app.domain.quotes.exceptions import (
    DuplicateQuote, InvalidQuoteState, QuoteExtractionFailure, QuoteNotFound,
)
from app.domain.quotes.value_objects import (
    EvidenceLocationType, QuoteDocumentStatus, QuoteExtractionRunStatus, QuoteStatus,
    confidence_band,
)
from app.domain.rfqs.value_objects import RfqStatus
from app.domain.suppliers.exceptions import SupplierNotFound
from app.domain.suppliers.value_objects import SupplierStatus


def _schema_hash(schema: dict[str, Any]) -> str:
    raw = json.dumps(schema, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _number(value: object, name: str) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise QuoteExtractionFailure(f"AI quote field {name} is not a valid number.") from exc
    if not result.is_finite() or result < 0:
        raise QuoteExtractionFailure(f"AI quote field {name} must be non-negative.")
    return result


def _document_response(item: QuoteDocument) -> QuoteDocumentResponse:
    return QuoteDocumentResponse(
        id=item.id, quote_id=item.quote_id, original_file_name=item.original_file_name,
        mime_type=item.mime_type, document_type=item.document_type,
        processing_status=item.processing_status, file_hash=item.file_hash, file_size=item.file_size,
        extractor_name=item.extractor_name, extractor_version=item.extractor_version,
        created_at=item.created_at,
    )


def _evidence_response(item: QuoteEvidenceReference) -> EvidenceResponse:
    return EvidenceResponse(
        id=item.id, quote_item_id=item.quote_item_id, quote_document_id=item.quote_document_id,
        extraction_run_id=item.extraction_run_id, field_name=item.field_name,
        location_type=item.location_type.value, location_label=item.location_label,
        fragment=item.fragment, method=item.method, confidence=item.confidence,
        created_at=item.created_at,
    )


def _detail(uow, quote: Quote) -> QuoteDetailResponse:
    evidence = uow.quotes.list_evidence(quote.id)
    by_item: dict[UUID, list[QuoteEvidenceReference]] = {}
    for ref in evidence:
        if ref.quote_item_id:
            by_item.setdefault(ref.quote_item_id, []).append(ref)
    items = tuple(
        QuoteItemReviewResponse(
            id=item.id, catalog_product_id=item.catalog_product_id, product_name=item.product_name,
            description=item.description, brand=item.brand, model=item.model, unit=item.unit,
            quantity=item.quantity, unit_price=item.unit_price, total_price=item.total_price,
            currency=item.currency, delivery_days=item.delivery_days,
            compliance_status=item.compliance_status, match_status=item.match_status,
            match_score=item.match_score, match_reason=item.match_reason,
            quoted_specifications=item.quoted_specifications, notes=item.notes,
            confidence=item.confidence, confidence_band=confidence_band(item.confidence),
            warnings=item.warnings,
            evidence=tuple(_evidence_response(ref) for ref in by_item.get(item.id, [])),
            original_extracted=item.original_extracted,
        )
        for item in uow.quotes.list_items(quote.id)
    )
    return QuoteDetailResponse(
        id=quote.id, tender_id=quote.tender_id, tender_supplier_id=quote.tender_supplier_id,
        supplier_id=quote.supplier_id, rfq_request_id=quote.rfq_request_id, status=quote.status,
        currency=quote.currency, subtotal_amount=quote.subtotal_amount, tax_amount=quote.tax_amount,
        total_amount=quote.total_amount, delivery_time_days=quote.delivery_time_days,
        commercial_terms=quote.commercial_terms, valid_until=quote.valid_until,
        received_at=quote.received_at, approved_extraction_run_id=quote.approved_extraction_run_id,
        version=quote.version, manual_edit_count=quote.manual_edit_count,
        reviewed_by_user_id=quote.reviewed_by_user_id, reviewed_at=quote.reviewed_at,
        rejection_reason=quote.rejection_reason, last_error=quote.last_error,
        documents=tuple(_document_response(doc) for doc in uow.quotes.list_documents(quote.id)),
        items=items, created_at=quote.created_at, updated_at=quote.updated_at,
    )


def _require_supplier_and_rfq(uow, tender_id: UUID, tender_supplier_id: UUID, rfq_request_id: UUID | None):
    tender = uow.tenders.get_by_id(tender_id)
    if tender is None:
        raise TenderNotFound("Tender was not found.")
    supplier = uow.suppliers.get_tender_supplier(tender_supplier_id)
    if supplier is None or supplier.tender_id != tender_id:
        raise SupplierNotFound("Tender supplier was not found.")
    if supplier.status not in {SupplierStatus.APPROVED, SupplierStatus.CONTACTED, SupplierStatus.RESPONDED}:
        raise InvalidQuoteState("Quote reception requires an approved tender supplier.")
    sent = [
        item for item in uow.rfqs.list_rfqs(tender_id)
        if item.tender_supplier_id == tender_supplier_id
        and item.status in {RfqStatus.SENT, RfqStatus.DELIVERED, RfqStatus.RESPONDED}
    ]
    if rfq_request_id is not None:
        matching = [item for item in sent if item.id == rfq_request_id]
        if not matching:
            raise InvalidQuoteState("Associated RFQ must be a sent RFQ for this supplier and tender.")
    elif not sent:
        raise InvalidQuoteState("Quote reception requires a previously sent RFQ for this supplier.")
    return tender, supplier, (rfq_request_id or sent[-1].id)


class ReceiveQuote:
    def __init__(self, uow_factory: UnitOfWorkFactory, storage: FileStorage, queue: QuoteAnalysisQueue, *, maximum_size_bytes: int) -> None:
        self._uow_factory = uow_factory
        self._storage = storage
        self._queue = queue
        self._validator = QuoteDocumentValidator(maximum_size_bytes)

    def execute(self, command: ReceiveQuoteCommand) -> tuple[QuoteDetailResponse, bool]:
        validated = self._validator.validate(command.file)
        with self._uow_factory() as uow:
            _, supplier, rfq_id = _require_supplier_and_rfq(
                uow, command.tender_id, command.tender_supplier_id, command.rfq_request_id
            )
            if not uow.users.exists(command.uploaded_by_user_id):
                raise InvalidQuoteState("Quote uploader user does not exist.")
            duplicate = uow.quotes.find_duplicate(command.tender_id, supplier.supplier_id, validated.file_hash.value)
            if duplicate is not None:
                uow.audit_events.append(quote_event(
                    duplicate.id, "QuoteDuplicateDetected", tender_id=str(command.tender_id),
                    supplier_id=str(supplier.supplier_id), file_hash=validated.file_hash.value,
                ))
                uow.commit()
                return _detail(uow, duplicate), True
            quote = Quote(
                tender_id=command.tender_id, tender_supplier_id=supplier.id,
                supplier_id=supplier.supplier_id, rfq_request_id=rfq_id,
                original_file_name=validated.original_file_name, storage_key="pending",
                mime_type=validated.mime_type, file_size=validated.file_size,
                file_hash=validated.file_hash.value, uploaded_by_user_id=command.uploaded_by_user_id,
            )
            storage_key: str | None = None
            try:
                storage_key = self._storage.store(command.tender_id, quote.id, validated.content)
                quote.storage_key = storage_key
                quote = uow.quotes.create_quote(quote)
                document = uow.quotes.create_document(QuoteDocument(
                    quote_id=quote.id, storage_key=storage_key,
                    original_file_name=validated.original_file_name, mime_type=validated.mime_type,
                    document_type="supplier_quote", file_hash=validated.file_hash.value,
                    file_size=validated.file_size,
                ))
                uow.audit_events.append(quote_event(
                    quote.id, "QuoteReceived", tender_id=str(quote.tender_id),
                    supplier_id=str(quote.supplier_id), rfq_request_id=str(rfq_id),
                    uploaded_by_user_id=str(command.uploaded_by_user_id), file_hash=quote.file_hash,
                ))
                uow.audit_events.append(quote_event(
                    quote.id, "QuoteFileStored", quote_document_id=str(document.id),
                    file_hash=document.file_hash, mime_type=document.mime_type, file_size=document.file_size,
                ))
                uow.commit()
            except Exception:
                uow.rollback()
                if storage_key:
                    with suppress(Exception):
                        self._storage.delete(storage_key)
                raise
        QueueQuoteProcessing(self._uow_factory, self._queue).execute(
            quote.id, command.correlation_id, force=False
        )
        with self._uow_factory() as uow:
            current = uow.quotes.get_quote(quote.id)
            assert current is not None
            return _detail(uow, current), False


class AddQuoteDocument:
    def __init__(self, uow_factory: UnitOfWorkFactory, storage: FileStorage, *, maximum_size_bytes: int) -> None:
        self._uow_factory=uow_factory; self._storage=storage; self._validator=QuoteDocumentValidator(maximum_size_bytes)

    def execute(self, command: AddQuoteDocumentCommand) -> QuoteDocumentResponse:
        validated=self._validator.validate(command.file)
        with self._uow_factory() as uow:
            quote=uow.quotes.get_quote(command.quote_id, for_update=True)
            if quote is None: raise QuoteNotFound("Quote was not found.")
            if quote.status in {QuoteStatus.APPROVED, QuoteStatus.REJECTED, QuoteStatus.INCLUDED_IN_COMPARISON}:
                raise InvalidQuoteState("Finalized quotes cannot receive additional documents.")
            if not uow.users.exists(command.uploaded_by_user_id): raise InvalidQuoteState("Uploader user does not exist.")
            for doc in uow.quotes.list_documents(quote.id):
                if doc.file_hash == validated.file_hash.value: return _document_response(doc)
            doc_id=uuid.uuid4(); key=self._storage.store(quote.tender_id, doc_id, validated.content)
            try:
                doc=uow.quotes.create_document(QuoteDocument(
                    id=doc_id, quote_id=quote.id, storage_key=key,
                    original_file_name=validated.original_file_name, mime_type=validated.mime_type,
                    document_type="supporting_quote", file_hash=validated.file_hash.value,
                    file_size=validated.file_size,
                ))
                uow.audit_events.append(quote_event(quote.id,"QuoteFileStored",quote_document_id=str(doc.id),file_hash=doc.file_hash,mime_type=doc.mime_type,file_size=doc.file_size))
                uow.commit(); return _document_response(doc)
            except Exception:
                uow.rollback()
                with suppress(Exception): self._storage.delete(key)
                raise


class QueueQuoteProcessing:
    def __init__(self, uow_factory: UnitOfWorkFactory, queue: QuoteAnalysisQueue) -> None:
        self._uow_factory=uow_factory; self._queue=queue

    def execute(self, quote_id: UUID, correlation_id: str | None, *, force: bool) -> str:
        correlation_id = correlation_id or str(uuid.uuid4())
        if force: correlation_id = f"reprocess:{correlation_id}:{uuid.uuid4()}"
        with self._uow_factory() as uow:
            quote=uow.quotes.get_quote(quote_id)
            if quote is None: raise QuoteNotFound("Quote was not found.")
            existing=uow.quotes.get_task_by_correlation(correlation_id)
            if existing is None:
                uow.quotes.create_task(QuoteTaskRecord(quote_id=quote_id, correlation_id=correlation_id))
                uow.audit_events.append(quote_event(quote_id,"QuoteReprocessed" if force else "QuoteAnalysisQueued",correlation_id=correlation_id))
                uow.commit()
        self._queue.enqueue(quote_id, correlation_id, force=force)
        return correlation_id


class ProcessQuote:
    def __init__(self, uow_factory: UnitOfWorkFactory, storage: FileStorage,
                 extractor: QuoteDocumentExtractor, ai_service: AIExtractionService,
                 prompts: PromptRegistry, *, prompt_version: str, model: str, temperature: float) -> None:
        self._uow_factory=uow_factory; self._storage=storage; self._extractor=extractor
        self._ai=ai_service; self._prompts=prompts; self._prompt_version=prompt_version
        self._model=model; self._temperature=temperature
        self._matcher=QuoteProductMatcher(); self._compliance=TechnicalComplianceEvaluator()

    def execute(self, quote_id: UUID, correlation_id: str | None = None, *, force: bool=False) -> UUID:
        prompt=self._prompts.get("quote_extraction", self._prompt_version)
        schema_hash=_schema_hash(prompt.output_schema)
        with self._uow_factory() as uow:
            quote=uow.quotes.get_quote(quote_id, for_update=True)
            if quote is None: raise QuoteNotFound("Quote was not found.")
            if quote.status in {QuoteStatus.APPROVED, QuoteStatus.INCLUDED_IN_COMPARISON, QuoteStatus.REJECTED}:
                raise InvalidQuoteState("Finalized quotes cannot be reprocessed.")
            docs=uow.quotes.list_documents(quote.id)
            if not docs: raise QuoteExtractionFailure("Quote has no stored document.")
            key_source="|".join(sorted(doc.file_hash for doc in docs)) + "|" + "|".join((
                self._extractor.version, self._model, prompt.version, prompt.schema_version, schema_hash
            ))
            if force: key_source += f"|force:{correlation_id or uuid.uuid4()}"
            key=hashlib.sha256(key_source.encode()).hexdigest()
            existing=uow.quotes.get_run_by_key(quote.id,key)
            if existing and existing.status in {QuoteExtractionRunStatus.COMPLETED, QuoteExtractionRunStatus.REUSED} and not force:
                return existing.id
            run=uow.quotes.create_run(QuoteExtractionRun(
                quote_id=quote.id,tender_id=quote.tender_id,supplier_id=quote.supplier_id,
                idempotency_key=key,extractor_version=self._extractor.version,
                prompt_version=prompt.version,model=self._model,schema_version=prompt.schema_version,
                schema_hash=schema_hash,
            ))
            if quote.status is QuoteStatus.RECEIVED: quote.start_validation(); quote.start_extraction()
            elif quote.status is QuoteStatus.VALIDATING: quote.start_extraction()
            elif quote.status in {QuoteStatus.PENDING_REVIEW, QuoteStatus.FAILED}: quote.start_extraction()
            elif quote.status not in {QuoteStatus.EXTRACTING}: raise InvalidQuoteState("Quote is not ready for processing.")
            run.start(); uow.quotes.update_quote(quote); uow.quotes.update_run(run)
            task=uow.quotes.get_task_by_correlation(correlation_id) if correlation_id else None
            if task: task.start(); uow.quotes.update_task(task)
            uow.audit_events.append(quote_event(quote.id,"QuoteAnalysisStarted",extraction_run_id=str(run.id),correlation_id=correlation_id,model=self._model,prompt_version=prompt.version,schema_version=prompt.schema_version))
            uow.commit()

        try:
            global_segments: list[tuple[QuoteDocument, Any]]=[]
            ordinal=1
            for doc in docs:
                doc.processing_status=QuoteDocumentStatus.PROCESSING
                result=self._extractor.extract(self._storage.read(doc.storage_key),doc.mime_type)
                doc.extractor_name=result.extractor_name; doc.extractor_version=result.extractor_version
                doc.processing_status=QuoteDocumentStatus.EXTRACTED
                for segment in result.segments:
                    global_segments.append((doc, segment))
                    ordinal += 1
            pages=tuple({
                "page_number": index,
                "text": segment.text,
                "source": {"document_id":str(doc.id),"location_type":segment.location_type,"location_label":segment.location_label,"method":segment.method},
                "tables": segment.tables,
            } for index,(doc,segment) in enumerate(global_segments,start=1))
            if not pages or not any(str(page["text"]).strip() for page in pages):
                raise QuoteExtractionFailure("Quote documents contain no extractable text.")
            ai=self._ai.extract(AIExtractionRequest(prompt=prompt,model=self._model,temperature=self._temperature,document_id=str(quote_id),pages=pages))
            raw_items=ai.payload.get("items")
            if not isinstance(raw_items,list) or not raw_items: raise QuoteExtractionFailure("AI quote response must contain at least one item.")
            normalized_text={i:" ".join(str(page["text"]).split()) for i,page in enumerate(pages,start=1)}
            with self._uow_factory() as uow:
                current=uow.quotes.get_quote(quote_id,for_update=True); current_run=uow.quotes.get_run(run.id,for_update=True)
                if current is None or current_run is None: raise QuoteNotFound("Quote processing state was not found.")
                snapshot=uow.catalogs.get_latest_snapshot(current.tender_id)
                if snapshot is None: raise InvalidQuoteState("Quote normalization requires an approved catalog.")
                items: list[QuoteItem]=[]; evidence_specs: list[tuple[QuoteItem,QuoteDocument,Any,dict[str,Any]]]=[]
                for raw in raw_items:
                    if not isinstance(raw,dict): raise QuoteExtractionFailure("AI quote item must be an object.")
                    name=str(raw.get("product_name") or "").strip()
                    if not name: raise QuoteExtractionFailure("AI quote item is missing product_name.")
                    ev=raw.get("evidence") or {}; position=int(ev.get("segment") or 0); fragment=" ".join(str(ev.get("fragment") or "").split())
                    if position<1 or position>len(global_segments) or not fragment or fragment not in normalized_text[position]:
                        raise QuoteExtractionFailure("Quote evidence is not grounded in its source segment.")
                    quantity=_number(raw.get("quantity"),"quantity"); unit_price=_number(raw.get("unit_price"),"unit_price"); total_price=_number(raw.get("total_price"),"total_price")
                    match=self._matcher.match(item_name=name,item_description=raw.get("description"),item_unit=raw.get("unit"),item_quantity=quantity,item_brand=raw.get("brand"),item_model=raw.get("model"),products=snapshot.products)
                    required={}
                    if match.product_id:
                        source=next((p for p in snapshot.products if str(p.get("product_id"))==str(match.product_id)),None)
                        if source: required=dict(source.get("specifications") or {})
                    quoted_specs={str(k):str(v) for k,v in (raw.get("specifications") or {}).items()}
                    compliance,reasons=self._compliance.evaluate(required,quoted_specs)
                    warnings=list(price_warnings(quantity,unit_price,total_price))
                    if match.status.value != "matched": warnings.append("PRODUCT_MATCH_REVIEW_REQUIRED")
                    if compliance.value in {"unknown","partial","non_compliant"}: warnings.append(f"TECHNICAL_{compliance.value.upper()}")
                    confidence=float(ev.get("confidence") or 0)
                    item=QuoteItem(
                        quote_id=current.id,extraction_run_id=current_run.id,catalog_product_id=match.product_id,
                        product_name=name,description=raw.get("description"),brand=raw.get("brand"),model=raw.get("model"),unit=raw.get("unit"),
                        quantity=quantity,unit_price=unit_price,total_price=total_price,currency=raw.get("currency"),
                        delivery_days=int(raw["delivery_days"]) if raw.get("delivery_days") is not None else None,
                        technical_compliance=None,compliance_status=compliance,match_status=match.status,match_score=match.score,match_reason=match.reason,
                        quoted_specifications=quoted_specs,notes=raw.get("notes"),source_page=position,evidence_fragment=fragment,
                        confidence=confidence,warnings=tuple(dict.fromkeys(warnings)),original_extracted=dict(raw),
                    )
                    items.append(item); doc,segment=global_segments[position-1]; evidence_specs.append((item,doc,segment,ev))
                persisted=uow.quotes.replace_items(current.id,tuple(items))
                persisted_by_id={item.id:item for item in persisted}
                for item,doc,segment,ev in evidence_specs:
                    fields=tuple(ev.get("fields") or ["item"])
                    first_id=None
                    for field_name in fields:
                        ref=uow.quotes.add_evidence(QuoteEvidenceReference(
                            quote_item_id=item.id,quote_document_id=doc.id,extraction_run_id=current_run.id,
                            field_name=str(field_name),location_type=EvidenceLocationType(segment.location_type),
                            location_label=segment.location_label,fragment=item.evidence_fragment or "",
                            method=segment.method,confidence=item.confidence,
                        ))
                        first_id=first_id or ref.id
                    if first_id:
                        p=persisted_by_id[item.id]; p.source_evidence_id=first_id; uow.quotes.update_item(p)
                summary=ai.payload.get("summary") or {}
                current.currency=(str(summary.get("currency")).upper() if summary.get("currency") else None)
                current.subtotal_amount=_number(summary.get("subtotal"),"subtotal")
                current.tax_amount=_number(summary.get("tax"),"tax")
                current.total_amount=_number(summary.get("total"),"total")
                current.delivery_time_days=int(summary["delivery_days"]) if summary.get("delivery_days") is not None else None
                current.commercial_terms=str(summary.get("commercial_terms"))[:10000] if summary.get("commercial_terms") else None
                current.mark_extracted(); current.mark_normalized(); current.last_error=None
                uow.quotes.update_quote(current)
                current_run.complete(provider_response_id=ai.provider_response_id,input_tokens=ai.input_tokens,output_tokens=ai.output_tokens,estimated_cost_usd=ai.estimated_cost_usd,raw_response=ai.payload,duration_ms=ai.duration_ms)
                uow.quotes.update_run(current_run)
                for doc in docs: uow.quotes.update_document(doc)
                task=uow.quotes.get_task_by_correlation(correlation_id) if correlation_id else None
                if task: task.complete(); uow.quotes.update_task(task)
                uow.audit_events.append(quote_event(current.id,"QuoteAnalyzed",extraction_run_id=str(current_run.id),item_count=len(items),model=ai.model,input_tokens=ai.input_tokens,output_tokens=ai.output_tokens,estimated_cost_usd=str(ai.estimated_cost_usd)))
                uow.audit_events.append(quote_event(current.id,"QuoteNormalized",extraction_run_id=str(current_run.id),warning_count=sum(len(i.warnings) for i in items)))
                uow.commit(); return current_run.id
        except Exception as exc:
            with self._uow_factory() as uow:
                current=uow.quotes.get_quote(quote_id,for_update=True); failed=uow.quotes.get_run(run.id,for_update=True)
                if current: current.record_error(exc,terminal=True); uow.quotes.update_quote(current)
                if failed: failed.fail(exc); uow.quotes.update_run(failed)
                task=uow.quotes.get_task_by_correlation(correlation_id) if correlation_id else None
                if task: task.fail(exc); uow.quotes.update_task(task)
                uow.commit()
            if isinstance(exc,QuoteExtractionFailure): raise
            raise QuoteExtractionFailure(str(exc)) from exc


class GetQuoteDetail:
    def __init__(self,uow_factory:UnitOfWorkFactory)->None:self._uow_factory=uow_factory
    def execute(self,quote_id:UUID)->QuoteDetailResponse:
        with self._uow_factory() as uow:
            quote=uow.quotes.get_quote(quote_id)
            if quote is None: raise QuoteNotFound("Quote was not found.")
            return _detail(uow,quote)


class GetProcessingStatus:
    def __init__(self,uow_factory:UnitOfWorkFactory)->None:self._uow_factory=uow_factory
    def execute(self,quote_id:UUID)->ProcessingStatusResponse:
        with self._uow_factory() as uow:
            quote=uow.quotes.get_quote(quote_id)
            if quote is None: raise QuoteNotFound("Quote was not found.")
            task=uow.quotes.get_latest_task(quote_id); runs=uow.quotes.list_runs(quote_id)
            return ProcessingStatusResponse(quote_id=quote_id,quote_status=quote.status,correlation_id=task.correlation_id if task else None,task_status=task.status.value if task else None,attempt_count=task.attempt_count if task else 0,extraction_runs=tuple({"id":str(run.id),"status":run.status.value,"provider":run.provider,"model":run.model,"prompt_version":run.prompt_version,"schema_version":run.schema_version,"extractor_version":run.extractor_version,"input_tokens":run.input_tokens,"output_tokens":run.output_tokens,"estimated_cost_usd":str(run.estimated_cost_usd),"started_at":run.started_at,"completed_at":run.completed_at,"error":run.error_message} for run in runs),last_error=quote.last_error)


class UpdateQuoteItem:
    def __init__(self,uow_factory:UnitOfWorkFactory)->None:self._uow_factory=uow_factory
    def execute(self,quote_id:UUID,item_id:UUID,command:UpdateQuoteItemCommand)->QuoteDetailResponse:
        with self._uow_factory() as uow:
            quote=uow.quotes.get_quote(quote_id,for_update=True); item=uow.quotes.get_item(item_id,for_update=True)
            if quote is None or item is None or item.quote_id!=quote_id: raise QuoteNotFound("Quote item was not found.")
            if quote.status is not QuoteStatus.PENDING_REVIEW: raise InvalidQuoteState("Quote items can only be corrected during human review.")
            if not uow.users.exists(command.changed_by_user_id): raise InvalidQuoteState("Review user does not exist.")
            changes={name:getattr(command,name) for name in command.__dataclass_fields__ if name!="changed_by_user_id" and getattr(command,name) is not None}
            if "catalog_product_id" in changes:
                product=uow.catalogs.get_product(changes["catalog_product_id"])
                if product is None or product.tender_id!=quote.tender_id or product.status is ProductStatus.REJECTED:
                    raise InvalidQuoteState("Quote item can only reference a valid non-rejected tender product.")
            before,after=item.apply_manual_correction(**changes)
            changed_fields=tuple(key for key in after if before.get(key)!=after.get(key))
            if changed_fields:
                uow.quotes.update_item(item); quote.record_manual_edit(); uow.quotes.update_quote(quote)
                uow.quotes.add_revision(QuoteItemRevision(quote_item_id=item.id,changed_by_user_id=command.changed_by_user_id,before=before,after=after,changed_fields=changed_fields))
                uow.audit_events.append(quote_event(quote.id,"QuoteItemCorrected",quote_item_id=str(item.id),changed_by_user_id=str(command.changed_by_user_id),changed_fields=list(changed_fields)))
                uow.commit()
            return _detail(uow,quote)


class SubmitQuoteForReview:
    def __init__(self,uow_factory:UnitOfWorkFactory)->None:self._uow_factory=uow_factory
    def execute(self,quote_id:UUID,user_id:UUID)->QuoteDetailResponse:
        with self._uow_factory() as uow:
            quote=uow.quotes.get_quote(quote_id,for_update=True)
            if quote is None: raise QuoteNotFound("Quote was not found.")
            if not uow.users.exists(user_id): raise InvalidQuoteState("Review user does not exist.")
            if quote.status is QuoteStatus.NORMALIZED: quote.start_review(); uow.quotes.update_quote(quote)
            elif quote.status is not QuoteStatus.PENDING_REVIEW: raise InvalidQuoteState("Only normalized quotes can be submitted for review.")
            uow.audit_events.append(quote_event(quote.id,"QuoteSubmittedForReview",user_id=str(user_id))); uow.commit(); return _detail(uow,quote)


class ApproveQuote:
    def __init__(self,uow_factory:UnitOfWorkFactory)->None:self._uow_factory=uow_factory
    def execute(self,quote_id:UUID,user_id:UUID)->QuoteDetailResponse:
        with self._uow_factory() as uow:
            quote=uow.quotes.get_quote(quote_id,for_update=True)
            if quote is None: raise QuoteNotFound("Quote was not found.")
            if quote.status is not QuoteStatus.PENDING_REVIEW: raise InvalidQuoteState("Quote must be in human review before approval.")
            if not uow.users.exists(user_id): raise InvalidQuoteState("Reviewer user does not exist.")
            items=uow.quotes.list_items(quote.id)
            if not items: raise InvalidQuoteState("Incomplete quote cannot be approved without items.")
            for item in items:
                if item.catalog_product_id is None or item.quantity is None or item.currency is None or (item.unit_price is None and item.total_price is None):
                    raise InvalidQuoteState("Incomplete quote item must be corrected before approval.")
                product=uow.catalogs.get_product(item.catalog_product_id)
                if product is None or product.tender_id!=quote.tender_id or product.status is ProductStatus.REJECTED:
                    raise InvalidQuoteState("Rejected or foreign products cannot be approved as comparable quote items.")
            completed=[run for run in uow.quotes.list_runs(quote.id) if run.status is QuoteExtractionRunStatus.COMPLETED]
            run_id=completed[-1].id if completed else None
            quote.approve(user_id,run_id); uow.quotes.update_quote(quote)
            uow.audit_events.append(quote_event(quote.id,"QuoteApproved",reviewer_user_id=str(user_id),extraction_run_id=str(run_id) if run_id else None)); uow.commit(); return _detail(uow,quote)


class RejectQuote:
    def __init__(self,uow_factory:UnitOfWorkFactory)->None:self._uow_factory=uow_factory
    def execute(self,quote_id:UUID,user_id:UUID,reason:str)->QuoteDetailResponse:
        with self._uow_factory() as uow:
            quote=uow.quotes.get_quote(quote_id,for_update=True)
            if quote is None: raise QuoteNotFound("Quote was not found.")
            if not uow.users.exists(user_id): raise InvalidQuoteState("Reviewer user does not exist.")
            quote.reject(user_id,reason); uow.quotes.update_quote(quote); uow.audit_events.append(quote_event(quote.id,"QuoteRejected",reviewer_user_id=str(user_id),reason=reason[:2000])); uow.commit(); return _detail(uow,quote)
