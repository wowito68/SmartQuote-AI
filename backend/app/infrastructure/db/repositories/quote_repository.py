from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.application.ports.quote_repository import QuoteRepository
from app.domain.comparisons.entities import ComparisonRun
from app.domain.quotes.entities import (
    Quote, QuoteDocument, QuoteEvidenceReference, QuoteExtractionRun, QuoteItem,
    QuoteItemRevision, QuoteTaskRecord,
)
from app.domain.quotes.value_objects import (
    ComplianceStatus, EvidenceLocationType, MatchStatus, QuoteDocumentStatus,
    QuoteExtractionRunStatus, QuoteStatus, QuoteTaskStatus,
)
from app.infrastructure.db.models.quote import (
    ComparisonRunModel, QuoteDocumentModel, QuoteEvidenceReferenceModel,
    QuoteExtractionRunModel, QuoteItemModel, QuoteItemRevisionModel, QuoteModel,
    QuoteTaskRecordModel,
)


def _quote_from_model(model: QuoteModel) -> Quote:
    return Quote(
        id=model.id, tender_id=model.tender_id, tender_supplier_id=model.tender_supplier_id,
        supplier_id=model.supplier_id, rfq_request_id=model.rfq_request_id,
        original_file_name=model.original_file_name, storage_key=model.storage_key,
        mime_type=model.mime_type, file_size=model.file_size, file_hash=model.file_hash,
        uploaded_by_user_id=model.uploaded_by_user_id, currency=model.currency,
        subtotal_amount=model.subtotal_amount, tax_amount=model.tax_amount,
        total_amount=model.total_amount, delivery_time_days=model.delivery_time_days,
        commercial_terms=model.commercial_terms, valid_until=model.valid_until,
        received_at=model.received_at, approved_extraction_run_id=model.approved_extraction_run_id,
        status=QuoteStatus(model.status), version=model.version, manual_edit_count=model.manual_edit_count,
        reviewed_by_user_id=model.reviewed_by_user_id, reviewed_at=model.reviewed_at,
        rejection_reason=model.rejection_reason, last_error=model.last_error,
        created_at=model.created_at, updated_at=model.updated_at,
    )


def _apply_quote(model: QuoteModel, quote: Quote) -> None:
    for name in (
        "rfq_request_id", "currency", "subtotal_amount", "tax_amount", "total_amount",
        "delivery_time_days", "commercial_terms", "valid_until", "received_at",
        "approved_extraction_run_id", "version", "manual_edit_count", "reviewed_by_user_id",
        "reviewed_at", "rejection_reason", "last_error", "updated_at",
    ):
        setattr(model, name, getattr(quote, name))
    model.status = quote.status.value


def _document_from_model(model: QuoteDocumentModel) -> QuoteDocument:
    return QuoteDocument(
        id=model.id, quote_id=model.quote_id, storage_key=model.storage_key,
        original_file_name=model.original_file_name, mime_type=model.mime_type,
        document_type=model.document_type, processing_status=QuoteDocumentStatus(model.processing_status),
        file_hash=model.file_hash, file_size=model.file_size, extractor_name=model.extractor_name,
        extractor_version=model.extractor_version, created_at=model.created_at,
    )


def _run_from_model(model: QuoteExtractionRunModel) -> QuoteExtractionRun:
    return QuoteExtractionRun(
        id=model.id, quote_id=model.quote_id, tender_id=model.tender_id, supplier_id=model.supplier_id,
        idempotency_key=model.idempotency_key, entity_type=model.entity_type, provider=model.provider,
        extractor_version=model.extractor_version, prompt_version=model.prompt_version, model=model.model,
        schema_version=model.schema_version, schema_hash=model.schema_hash,
        status=QuoteExtractionRunStatus(model.status), provider_response_id=model.provider_response_id,
        input_tokens=model.input_tokens, output_tokens=model.output_tokens,
        estimated_cost_usd=model.estimated_cost_usd, duration_ms=model.duration_ms,
        raw_response=model.raw_response, error_type=model.error_type, error_message=model.error_message,
        started_at=model.started_at, completed_at=model.completed_at, created_at=model.created_at,
    )


def _item_from_model(model: QuoteItemModel) -> QuoteItem:
    return QuoteItem(
        id=model.id, quote_id=model.quote_id, extraction_run_id=model.extraction_run_id,
        catalog_product_id=model.catalog_product_id, product_name=model.product_name,
        description=model.description, brand=model.brand, model=model.model, unit=model.unit,
        quantity=model.quantity, unit_price=model.unit_price, total_price=model.total_price,
        currency=model.currency, delivery_days=model.delivery_days,
        technical_compliance=model.technical_compliance,
        compliance_status=ComplianceStatus(model.compliance_status), match_status=MatchStatus(model.match_status),
        match_score=model.match_score, match_reason=model.match_reason,
        quoted_specifications=dict(model.quoted_specifications or {}), notes=model.notes,
        source_page=model.source_page, evidence_fragment=model.evidence_fragment,
        source_evidence_id=model.source_evidence_id, confidence=model.confidence,
        warnings=tuple(model.warnings or []), original_extracted=dict(model.original_extracted or {}),
        is_current=model.is_current, created_at=model.created_at, updated_at=model.updated_at,
    )


def _evidence_from_model(model: QuoteEvidenceReferenceModel) -> QuoteEvidenceReference:
    return QuoteEvidenceReference(
        id=model.id, quote_item_id=model.quote_item_id, quote_document_id=model.quote_document_id,
        extraction_run_id=model.extraction_run_id, field_name=model.field_name,
        location_type=EvidenceLocationType(model.location_type), location_label=model.location_label,
        fragment=model.fragment, method=model.method, confidence=model.confidence, created_at=model.created_at,
    )


def _task_from_model(model: QuoteTaskRecordModel) -> QuoteTaskRecord:
    return QuoteTaskRecord(
        id=model.id, quote_id=model.quote_id, correlation_id=model.correlation_id,
        status=QuoteTaskStatus(model.status), attempt_count=model.attempt_count, queued_at=model.queued_at,
        started_at=model.started_at, completed_at=model.completed_at,
        error_type=model.error_type, error_message=model.error_message,
    )


def _comparison_from_model(model: ComparisonRunModel) -> ComparisonRun:
    return ComparisonRun(
        id=model.id, tender_id=model.tender_id, catalog_snapshot_id=model.catalog_snapshot_id,
        comparison_key=model.comparison_key, approved_quotes_version=model.approved_quotes_version,
        scoring_config_version=model.scoring_config_version, rows=tuple(model.rows),
        recommendation=model.recommendation, generated_by_user_id=model.generated_by_user_id,
        created_at=model.created_at,
    )


class SqlAlchemyQuoteRepository(QuoteRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_quote(self, quote: Quote) -> Quote:
        model = QuoteModel(
            id=quote.id, tender_id=quote.tender_id, tender_supplier_id=quote.tender_supplier_id,
            supplier_id=quote.supplier_id, rfq_request_id=quote.rfq_request_id,
            original_file_name=quote.original_file_name, storage_key=quote.storage_key,
            mime_type=quote.mime_type, file_size=quote.file_size, file_hash=quote.file_hash,
            uploaded_by_user_id=quote.uploaded_by_user_id, currency=quote.currency,
            subtotal_amount=quote.subtotal_amount, tax_amount=quote.tax_amount, total_amount=quote.total_amount,
            delivery_time_days=quote.delivery_time_days, commercial_terms=quote.commercial_terms,
            valid_until=quote.valid_until, received_at=quote.received_at,
            approved_extraction_run_id=quote.approved_extraction_run_id, status=quote.status.value,
            version=quote.version, manual_edit_count=quote.manual_edit_count,
            reviewed_by_user_id=quote.reviewed_by_user_id, reviewed_at=quote.reviewed_at,
            rejection_reason=quote.rejection_reason, last_error=quote.last_error,
            created_at=quote.created_at, updated_at=quote.updated_at,
        )
        self._session.add(model); self._session.flush(); return _quote_from_model(model)

    def update_quote(self, quote: Quote) -> Quote:
        model = self._session.get(QuoteModel, quote.id)
        if model is None: raise ValueError("Quote does not exist.")
        _apply_quote(model, quote); self._session.flush(); return _quote_from_model(model)

    def get_quote(self, quote_id: UUID, *, for_update: bool = False) -> Quote | None:
        stmt = select(QuoteModel).where(QuoteModel.id == quote_id)
        if for_update: stmt = stmt.with_for_update()
        model = self._session.scalars(stmt).first(); return _quote_from_model(model) if model else None

    def find_duplicate(self, tender_id: UUID, supplier_id: UUID, file_hash: str) -> Quote | None:
        model = self._session.scalars(select(QuoteModel).where(
            QuoteModel.tender_id == tender_id, QuoteModel.supplier_id == supplier_id,
            QuoteModel.file_hash == file_hash,
        )).first(); return _quote_from_model(model) if model else None

    def list_quotes(self, tender_id: UUID) -> list[Quote]:
        return [_quote_from_model(m) for m in self._session.scalars(
            select(QuoteModel).where(QuoteModel.tender_id == tender_id).order_by(QuoteModel.created_at, QuoteModel.id)
        )]

    def list_quotes_by_status(self, tender_id: UUID, statuses: set[QuoteStatus]) -> list[Quote]:
        return [_quote_from_model(m) for m in self._session.scalars(select(QuoteModel).where(
            QuoteModel.tender_id == tender_id, QuoteModel.status.in_([s.value for s in statuses])
        ))]

    def create_document(self, document: QuoteDocument) -> QuoteDocument:
        model = QuoteDocumentModel(
            id=document.id, quote_id=document.quote_id, storage_key=document.storage_key,
            original_file_name=document.original_file_name, mime_type=document.mime_type,
            document_type=document.document_type, processing_status=document.processing_status.value,
            file_hash=document.file_hash, file_size=document.file_size, extractor_name=document.extractor_name,
            extractor_version=document.extractor_version, created_at=document.created_at,
        ); self._session.add(model); self._session.flush(); return _document_from_model(model)

    def update_document(self, document: QuoteDocument) -> QuoteDocument:
        model = self._session.get(QuoteDocumentModel, document.id)
        if model is None: raise ValueError("Quote document does not exist.")
        model.processing_status=document.processing_status.value; model.extractor_name=document.extractor_name
        model.extractor_version=document.extractor_version; self._session.flush(); return _document_from_model(model)

    def list_documents(self, quote_id: UUID) -> list[QuoteDocument]:
        return [_document_from_model(m) for m in self._session.scalars(select(QuoteDocumentModel).where(
            QuoteDocumentModel.quote_id == quote_id).order_by(QuoteDocumentModel.created_at, QuoteDocumentModel.id))]

    def get_document(self, document_id: UUID) -> QuoteDocument | None:
        model=self._session.get(QuoteDocumentModel, document_id); return _document_from_model(model) if model else None

    def create_run(self, run: QuoteExtractionRun) -> QuoteExtractionRun:
        model = QuoteExtractionRunModel(
            id=run.id, quote_id=run.quote_id, tender_id=run.tender_id, supplier_id=run.supplier_id,
            idempotency_key=run.idempotency_key, entity_type=run.entity_type, provider=run.provider,
            extractor_version=run.extractor_version, prompt_version=run.prompt_version, model=run.model,
            schema_version=run.schema_version, schema_hash=run.schema_hash, status=run.status.value,
            provider_response_id=run.provider_response_id, input_tokens=run.input_tokens,
            output_tokens=run.output_tokens, estimated_cost_usd=run.estimated_cost_usd,
            duration_ms=run.duration_ms, raw_response=run.raw_response, error_type=run.error_type,
            error_message=run.error_message, started_at=run.started_at, completed_at=run.completed_at,
            created_at=run.created_at,
        ); self._session.add(model); self._session.flush(); return _run_from_model(model)

    def update_run(self, run: QuoteExtractionRun) -> QuoteExtractionRun:
        model=self._session.get(QuoteExtractionRunModel, run.id)
        if model is None: raise ValueError("Quote extraction run does not exist.")
        for name in ("provider_response_id","input_tokens","output_tokens","estimated_cost_usd","duration_ms","raw_response","error_type","error_message","started_at","completed_at"):
            setattr(model,name,getattr(run,name))
        model.status=run.status.value; self._session.flush(); return _run_from_model(model)

    def get_run(self, run_id: UUID, *, for_update: bool = False) -> QuoteExtractionRun | None:
        stmt=select(QuoteExtractionRunModel).where(QuoteExtractionRunModel.id==run_id)
        if for_update: stmt=stmt.with_for_update()
        model=self._session.scalars(stmt).first(); return _run_from_model(model) if model else None

    def get_run_by_key(self, quote_id: UUID, key: str) -> QuoteExtractionRun | None:
        model=self._session.scalars(select(QuoteExtractionRunModel).where(
            QuoteExtractionRunModel.quote_id==quote_id, QuoteExtractionRunModel.idempotency_key==key)).first()
        return _run_from_model(model) if model else None

    def list_runs(self, quote_id: UUID) -> list[QuoteExtractionRun]:
        return [_run_from_model(m) for m in self._session.scalars(select(QuoteExtractionRunModel).where(
            QuoteExtractionRunModel.quote_id==quote_id).order_by(QuoteExtractionRunModel.created_at))]

    def replace_items(self, quote_id: UUID, items: tuple[QuoteItem, ...]) -> tuple[QuoteItem, ...]:
        # Compatibility name: preserve historical items and rotate current candidates.
        self._session.execute(update(QuoteItemModel).where(
            QuoteItemModel.quote_id==quote_id, QuoteItemModel.is_current.is_(True)).values(is_current=False))
        return self.create_items(items)

    def create_items(self, items: tuple[QuoteItem, ...]) -> tuple[QuoteItem, ...]:
        models=[]
        for item in items:
            model=QuoteItemModel(
                id=item.id, quote_id=item.quote_id, extraction_run_id=item.extraction_run_id,
                catalog_product_id=item.catalog_product_id, product_name=item.product_name,
                description=item.description, brand=item.brand, model=item.model, unit=item.unit,
                quantity=item.quantity, unit_price=item.unit_price, total_price=item.total_price,
                currency=item.currency, delivery_days=item.delivery_days,
                technical_compliance=item.technical_compliance, compliance_status=item.compliance_status.value,
                match_status=item.match_status.value, match_score=item.match_score, match_reason=item.match_reason,
                quoted_specifications=item.quoted_specifications, notes=item.notes, source_page=item.source_page,
                evidence_fragment=item.evidence_fragment, source_evidence_id=item.source_evidence_id,
                confidence=item.confidence, warnings=list(item.warnings), original_extracted=item.original_extracted,
                is_current=item.is_current, created_at=item.created_at, updated_at=item.updated_at,
            ); models.append(model)
        self._session.add_all(models); self._session.flush(); return tuple(_item_from_model(m) for m in models)

    def list_items(self, quote_id: UUID) -> list[QuoteItem]:
        return [_item_from_model(m) for m in self._session.scalars(select(QuoteItemModel).where(
            QuoteItemModel.quote_id==quote_id, QuoteItemModel.is_current.is_(True)).order_by(QuoteItemModel.created_at, QuoteItemModel.id))]

    def list_all_items(self, quote_id: UUID) -> list[QuoteItem]:
        return [_item_from_model(m) for m in self._session.scalars(select(QuoteItemModel).where(
            QuoteItemModel.quote_id==quote_id).order_by(QuoteItemModel.created_at, QuoteItemModel.id))]

    def get_item(self, item_id: UUID, *, for_update: bool=False) -> QuoteItem | None:
        stmt=select(QuoteItemModel).where(QuoteItemModel.id==item_id)
        if for_update: stmt=stmt.with_for_update()
        model=self._session.scalars(stmt).first(); return _item_from_model(model) if model else None

    def update_item(self, item: QuoteItem) -> QuoteItem:
        model=self._session.get(QuoteItemModel,item.id)
        if model is None: raise ValueError("Quote item does not exist.")
        for name in ("catalog_product_id","brand","model","unit","quantity","unit_price","total_price","currency","delivery_days","match_score","match_reason","notes","source_evidence_id","confidence","is_current","updated_at"):
            setattr(model,name,getattr(item,name))
        model.compliance_status=item.compliance_status.value; model.match_status=item.match_status.value
        model.technical_compliance=item.technical_compliance; model.warnings=list(item.warnings)
        self._session.flush(); return _item_from_model(model)

    def add_evidence(self, evidence: QuoteEvidenceReference) -> QuoteEvidenceReference:
        model=QuoteEvidenceReferenceModel(
            id=evidence.id, quote_item_id=evidence.quote_item_id, quote_document_id=evidence.quote_document_id,
            extraction_run_id=evidence.extraction_run_id, field_name=evidence.field_name,
            location_type=evidence.location_type.value, location_label=evidence.location_label,
            fragment=evidence.fragment, method=evidence.method, confidence=evidence.confidence,
            created_at=evidence.created_at,
        ); self._session.add(model); self._session.flush(); return _evidence_from_model(model)

    def list_evidence(self, quote_id: UUID) -> list[QuoteEvidenceReference]:
        return [_evidence_from_model(m) for m in self._session.scalars(
            select(QuoteEvidenceReferenceModel).join(QuoteDocumentModel).where(QuoteDocumentModel.quote_id==quote_id)
            .order_by(QuoteEvidenceReferenceModel.created_at))]

    def add_revision(self, revision: QuoteItemRevision) -> QuoteItemRevision:
        self._session.add(QuoteItemRevisionModel(
            id=revision.id, quote_item_id=revision.quote_item_id,
            changed_by_user_id=revision.changed_by_user_id, before=revision.before, after=revision.after,
            changed_fields=list(revision.changed_fields), created_at=revision.created_at,
        )); self._session.flush(); return revision

    def create_task(self, task: QuoteTaskRecord) -> QuoteTaskRecord:
        model=QuoteTaskRecordModel(id=task.id, quote_id=task.quote_id, correlation_id=task.correlation_id,
            status=task.status.value, attempt_count=task.attempt_count, queued_at=task.queued_at,
            started_at=task.started_at, completed_at=task.completed_at, error_type=task.error_type,
            error_message=task.error_message)
        self._session.add(model); self._session.flush(); return _task_from_model(model)

    def update_task(self, task: QuoteTaskRecord) -> QuoteTaskRecord:
        model=self._session.get(QuoteTaskRecordModel, task.id)
        if model is None: raise ValueError("Quote task does not exist.")
        model.status=task.status.value; model.attempt_count=task.attempt_count; model.started_at=task.started_at
        model.completed_at=task.completed_at; model.error_type=task.error_type; model.error_message=task.error_message
        self._session.flush(); return _task_from_model(model)

    def get_task_by_correlation(self, correlation_id: str) -> QuoteTaskRecord | None:
        model=self._session.scalars(select(QuoteTaskRecordModel).where(QuoteTaskRecordModel.correlation_id==correlation_id)).first()
        return _task_from_model(model) if model else None

    def get_latest_task(self, quote_id: UUID) -> QuoteTaskRecord | None:
        model=self._session.scalars(select(QuoteTaskRecordModel).where(QuoteTaskRecordModel.quote_id==quote_id)
            .order_by(QuoteTaskRecordModel.queued_at.desc()).limit(1)).first()
        return _task_from_model(model) if model else None

    def create_comparison(self, comparison: ComparisonRun) -> ComparisonRun:
        model=ComparisonRunModel(id=comparison.id,tender_id=comparison.tender_id,catalog_snapshot_id=comparison.catalog_snapshot_id,
            comparison_key=comparison.comparison_key,approved_quotes_version=comparison.approved_quotes_version,
            scoring_config_version=comparison.scoring_config_version,rows=list(comparison.rows),recommendation=comparison.recommendation,
            generated_by_user_id=comparison.generated_by_user_id,created_at=comparison.created_at)
        self._session.add(model); self._session.flush(); return _comparison_from_model(model)

    def get_comparison_by_key(self, tender_id: UUID, key: str) -> ComparisonRun | None:
        model=self._session.scalars(select(ComparisonRunModel).where(ComparisonRunModel.tender_id==tender_id,ComparisonRunModel.comparison_key==key)).first()
        return _comparison_from_model(model) if model else None

    def get_latest_comparison(self, tender_id: UUID) -> ComparisonRun | None:
        model=self._session.scalars(select(ComparisonRunModel).where(ComparisonRunModel.tender_id==tender_id).order_by(ComparisonRunModel.created_at.desc()).limit(1)).first()
        return _comparison_from_model(model) if model else None
