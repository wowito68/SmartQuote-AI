from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.application.ports.quote_repository import QuoteRepository
from app.domain.comparisons.entities import ComparisonRun
from app.domain.quotes.entities import (
    Quote,
    QuoteDocument,
    QuoteEvidenceReference,
    QuoteExtractionRun,
    QuoteItem,
    QuoteItemRevision,
    QuoteTaskRecord,
)
from app.domain.quotes.value_objects import (
    ComplianceStatus,
    EvidenceFindingStatus,
    ProductMatchStatus,
    QuoteDocumentProcessingStatus,
    QuoteDocumentType,
    QuoteExtractionRunStatus,
    QuoteStatus,
    QuoteTaskStatus,
)
from app.infrastructure.db.models.quote import (
    ComparisonRunModel,
    QuoteDocumentModel,
    QuoteEvidenceReferenceModel,
    QuoteExtractionRunModel,
    QuoteItemModel,
    QuoteItemRevisionModel,
    QuoteModel,
    QuoteTaskRecordModel,
)


def _quote_from_model(model: QuoteModel) -> Quote:
    return Quote(
        id=model.id,
        tender_id=model.tender_id,
        tender_supplier_id=model.tender_supplier_id,
        supplier_id=model.supplier_id,
        rfq_request_id=model.rfq_request_id,
        original_file_name=model.original_file_name,
        storage_key=model.storage_key,
        mime_type=model.mime_type,
        file_size=model.file_size,
        file_hash=model.file_hash,
        uploaded_by_user_id=model.uploaded_by_user_id,
        status=QuoteStatus(model.status),
        currency=model.currency,
        subtotal_amount=model.subtotal_amount,
        tax_amount=model.tax_amount,
        total_amount=model.total_amount,
        delivery_time_days=model.delivery_time_days,
        commercial_terms=model.commercial_terms,
        valid_until=model.valid_until,
        received_at=model.received_at,
        approved_extraction_run_id=model.approved_extraction_run_id,
        version=model.version,
        manual_edit_count=model.manual_edit_count,
        reviewed_by_user_id=model.reviewed_by_user_id,
        reviewed_at=model.reviewed_at,
        rejection_reason=model.rejection_reason,
        last_error=model.last_error,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _apply_quote(model: QuoteModel, quote: Quote) -> None:
    model.rfq_request_id = quote.rfq_request_id
    model.status = quote.status.value
    model.currency = quote.currency
    model.subtotal_amount = quote.subtotal_amount
    model.tax_amount = quote.tax_amount
    model.total_amount = quote.total_amount
    model.delivery_time_days = quote.delivery_time_days
    model.commercial_terms = quote.commercial_terms
    model.valid_until = quote.valid_until
    model.received_at = quote.received_at
    model.approved_extraction_run_id = quote.approved_extraction_run_id
    model.version = quote.version
    model.manual_edit_count = quote.manual_edit_count
    model.reviewed_by_user_id = quote.reviewed_by_user_id
    model.reviewed_at = quote.reviewed_at
    model.rejection_reason = quote.rejection_reason
    model.last_error = quote.last_error
    model.updated_at = quote.updated_at


def _document_from_model(model: QuoteDocumentModel) -> QuoteDocument:
    return QuoteDocument(
        id=model.id,
        quote_id=model.quote_id,
        storage_key=model.storage_key,
        original_file_name=model.original_file_name,
        mime_type=model.mime_type,
        file_size=model.file_size,
        file_hash=model.file_hash,
        document_type=QuoteDocumentType(model.document_type),
        processing_status=QuoteDocumentProcessingStatus(model.processing_status),
        extractor_name=model.extractor_name,
        extractor_version=model.extractor_version,
        last_error=model.last_error,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _run_from_model(model: QuoteExtractionRunModel) -> QuoteExtractionRun:
    return QuoteExtractionRun(
        id=model.id,
        quote_id=model.quote_id,
        quote_document_id=model.quote_document_id,
        tender_id=model.tender_id,
        supplier_id=model.supplier_id,
        idempotency_key=model.idempotency_key,
        extraction_fingerprint=model.extraction_fingerprint,
        run_number=model.run_number,
        provider=model.provider,
        extractor_name=model.extractor_name,
        extractor_version=model.extractor_version,
        prompt_version=model.prompt_version,
        model=model.model,
        schema_version=model.schema_version,
        schema_hash=model.schema_hash,
        status=QuoteExtractionRunStatus(model.status),
        provider_response_id=model.provider_response_id,
        input_tokens=model.input_tokens,
        output_tokens=model.output_tokens,
        estimated_cost_usd=model.estimated_cost_usd,
        duration_ms=model.duration_ms,
        raw_response=model.raw_response,
        error_type=model.error_type,
        error_message=model.error_message,
        reused_from_run_id=model.reused_from_run_id,
        is_approved_source=model.is_approved_source,
        started_at=model.started_at,
        completed_at=model.completed_at,
        created_at=model.created_at,
    )


def _item_from_model(model: QuoteItemModel) -> QuoteItem:
    return QuoteItem(
        id=model.id,
        quote_id=model.quote_id,
        extraction_run_id=model.extraction_run_id,
        catalog_product_id=model.catalog_product_id,
        product_name=model.product_name,
        description=model.description,
        brand=model.brand,
        model=model.model,
        quantity=model.quantity,
        unit=model.unit,
        unit_price=model.unit_price,
        total_price=model.total_price,
        currency=model.currency,
        delivery_days=model.delivery_days,
        technical_compliance=model.technical_compliance,
        compliance_status=ComplianceStatus(model.compliance_status),
        quoted_specifications=dict(model.quoted_specifications or {}),
        match_status=ProductMatchStatus(model.match_status),
        match_score=model.match_score,
        match_reason=model.match_reason,
        warnings=tuple(model.warnings or []),
        notes=model.notes,
        source_evidence_id=model.source_evidence_id,
        source_page=model.source_page,
        evidence_fragment=model.evidence_fragment,
        confidence=model.confidence,
        original_extracted=dict(model.original_extracted or {}),
        is_current=model.is_current,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _evidence_from_model(model: QuoteEvidenceReferenceModel) -> QuoteEvidenceReference:
    return QuoteEvidenceReference(
        id=model.id,
        quote_id=model.quote_id,
        quote_document_id=model.quote_document_id,
        extraction_run_id=model.extraction_run_id,
        entity_type=model.entity_type,
        entity_id=model.entity_id,
        field_name=model.field_name,
        locator_type=model.locator_type,
        locator=model.locator,
        fragment=model.fragment,
        extraction_method=model.extraction_method,
        finding_status=EvidenceFindingStatus(model.finding_status),
        confidence=model.confidence,
        created_at=model.created_at,
    )


def _revision_from_model(model: QuoteItemRevisionModel) -> QuoteItemRevision:
    return QuoteItemRevision(
        id=model.id,
        quote_id=model.quote_id,
        quote_item_id=model.quote_item_id,
        changed_by_user_id=model.changed_by_user_id,
        before=dict(model.before),
        after=dict(model.after),
        changed_fields=tuple(model.changed_fields or []),
        created_at=model.created_at,
    )


def _task_from_model(model: QuoteTaskRecordModel) -> QuoteTaskRecord:
    return QuoteTaskRecord(
        id=model.id,
        quote_id=model.quote_id,
        correlation_id=model.correlation_id,
        task_name=model.task_name,
        status=QuoteTaskStatus(model.status),
        attempt_count=model.attempt_count,
        force_reprocess=model.force_reprocess,
        last_error=model.last_error,
        queued_at=model.queued_at,
        started_at=model.started_at,
        completed_at=model.completed_at,
        updated_at=model.updated_at,
    )


def _comparison_from_model(model: ComparisonRunModel) -> ComparisonRun:
    return ComparisonRun(
        id=model.id,
        tender_id=model.tender_id,
        catalog_snapshot_id=model.catalog_snapshot_id,
        comparison_key=model.comparison_key,
        approved_quotes_version=model.approved_quotes_version,
        scoring_config_version=model.scoring_config_version,
        rows=tuple(model.rows),
        recommendation=model.recommendation,
        generated_by_user_id=model.generated_by_user_id,
        created_at=model.created_at,
    )


class SqlAlchemyQuoteRepository(QuoteRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_quote(self, quote: Quote) -> Quote:
        model = QuoteModel(
            id=quote.id,
            tender_id=quote.tender_id,
            tender_supplier_id=quote.tender_supplier_id,
            supplier_id=quote.supplier_id,
            rfq_request_id=quote.rfq_request_id,
            original_file_name=quote.original_file_name,
            storage_key=quote.storage_key,
            mime_type=quote.mime_type,
            file_size=quote.file_size,
            file_hash=quote.file_hash,
            uploaded_by_user_id=quote.uploaded_by_user_id,
            status=quote.status.value,
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
            created_at=quote.created_at,
            updated_at=quote.updated_at,
        )
        self._session.add(model)
        self._session.flush()
        return _quote_from_model(model)

    def update_quote(self, quote: Quote) -> Quote:
        model = self._session.get(QuoteModel, quote.id)
        if model is None:
            raise ValueError("Quote does not exist.")
        _apply_quote(model, quote)
        self._session.flush()
        return _quote_from_model(model)

    def get_quote(self, quote_id: UUID, *, for_update: bool = False) -> Quote | None:
        statement = select(QuoteModel).where(QuoteModel.id == quote_id)
        if for_update:
            statement = statement.with_for_update()
        model = self._session.scalars(statement).first()
        return _quote_from_model(model) if model else None

    def find_duplicate(self, tender_id: UUID, supplier_id: UUID, file_hash: str) -> Quote | None:
        model = self._session.scalars(
            select(QuoteModel).where(
                QuoteModel.tender_id == tender_id,
                QuoteModel.supplier_id == supplier_id,
                QuoteModel.file_hash == file_hash,
            )
        ).first()
        return _quote_from_model(model) if model else None

    def list_quotes(self, tender_id: UUID) -> list[Quote]:
        return [
            _quote_from_model(model)
            for model in self._session.scalars(
                select(QuoteModel)
                .where(QuoteModel.tender_id == tender_id)
                .order_by(QuoteModel.created_at, QuoteModel.id)
            )
        ]

    def list_quotes_by_status(self, tender_id: UUID, statuses: set[QuoteStatus]) -> list[Quote]:
        return [
            _quote_from_model(model)
            for model in self._session.scalars(
                select(QuoteModel).where(
                    QuoteModel.tender_id == tender_id,
                    QuoteModel.status.in_([status.value for status in statuses]),
                )
            )
        ]

    def create_document(self, document: QuoteDocument) -> QuoteDocument:
        model = QuoteDocumentModel(
            id=document.id,
            quote_id=document.quote_id,
            storage_key=document.storage_key,
            original_file_name=document.original_file_name,
            mime_type=document.mime_type,
            file_size=document.file_size,
            file_hash=document.file_hash,
            document_type=document.document_type.value,
            processing_status=document.processing_status.value,
            extractor_name=document.extractor_name,
            extractor_version=document.extractor_version,
            last_error=document.last_error,
            created_at=document.created_at,
            updated_at=document.updated_at,
        )
        self._session.add(model)
        self._session.flush()
        return _document_from_model(model)

    def update_document(self, document: QuoteDocument) -> QuoteDocument:
        model = self._session.get(QuoteDocumentModel, document.id)
        if model is None:
            raise ValueError("Quote document does not exist.")
        model.processing_status = document.processing_status.value
        model.extractor_name = document.extractor_name
        model.extractor_version = document.extractor_version
        model.last_error = document.last_error
        model.updated_at = document.updated_at
        self._session.flush()
        return _document_from_model(model)

    def get_document(self, document_id: UUID, *, for_update: bool = False) -> QuoteDocument | None:
        statement = select(QuoteDocumentModel).where(QuoteDocumentModel.id == document_id)
        if for_update:
            statement = statement.with_for_update()
        model = self._session.scalars(statement).first()
        return _document_from_model(model) if model else None

    def list_documents(self, quote_id: UUID) -> list[QuoteDocument]:
        return [
            _document_from_model(model)
            for model in self._session.scalars(
                select(QuoteDocumentModel)
                .where(QuoteDocumentModel.quote_id == quote_id)
                .order_by(QuoteDocumentModel.created_at, QuoteDocumentModel.id)
            )
        ]

    def create_run(self, run: QuoteExtractionRun) -> QuoteExtractionRun:
        model = QuoteExtractionRunModel(
            id=run.id,
            quote_id=run.quote_id,
            quote_document_id=run.quote_document_id,
            tender_id=run.tender_id,
            supplier_id=run.supplier_id,
            idempotency_key=run.idempotency_key,
            extraction_fingerprint=run.extraction_fingerprint,
            run_number=run.run_number,
            provider=run.provider,
            extractor_name=run.extractor_name,
            extractor_version=run.extractor_version,
            prompt_version=run.prompt_version,
            model=run.model,
            schema_version=run.schema_version,
            schema_hash=run.schema_hash,
            status=run.status.value,
            provider_response_id=run.provider_response_id,
            input_tokens=run.input_tokens,
            output_tokens=run.output_tokens,
            estimated_cost_usd=run.estimated_cost_usd,
            duration_ms=run.duration_ms,
            raw_response=run.raw_response,
            error_type=run.error_type,
            error_message=run.error_message,
            reused_from_run_id=run.reused_from_run_id,
            is_approved_source=run.is_approved_source,
            started_at=run.started_at,
            completed_at=run.completed_at,
            created_at=run.created_at,
        )
        self._session.add(model)
        self._session.flush()
        return _run_from_model(model)

    def update_run(self, run: QuoteExtractionRun) -> QuoteExtractionRun:
        model = self._session.get(QuoteExtractionRunModel, run.id)
        if model is None:
            raise ValueError("Quote extraction run does not exist.")
        model.status = run.status.value
        model.provider_response_id = run.provider_response_id
        model.input_tokens = run.input_tokens
        model.output_tokens = run.output_tokens
        model.estimated_cost_usd = run.estimated_cost_usd
        model.duration_ms = run.duration_ms
        model.raw_response = run.raw_response
        model.error_type = run.error_type
        model.error_message = run.error_message
        model.reused_from_run_id = run.reused_from_run_id
        model.is_approved_source = run.is_approved_source
        model.started_at = run.started_at
        model.completed_at = run.completed_at
        self._session.flush()
        return _run_from_model(model)

    def get_run(self, run_id: UUID, *, for_update: bool = False) -> QuoteExtractionRun | None:
        statement = select(QuoteExtractionRunModel).where(QuoteExtractionRunModel.id == run_id)
        if for_update:
            statement = statement.with_for_update()
        model = self._session.scalars(statement).first()
        return _run_from_model(model) if model else None

    def get_run_by_key(self, quote_id: UUID, key: str) -> QuoteExtractionRun | None:
        model = self._session.scalars(
            select(QuoteExtractionRunModel).where(
                QuoteExtractionRunModel.quote_id == quote_id,
                QuoteExtractionRunModel.idempotency_key == key,
            )
        ).first()
        return _run_from_model(model) if model else None

    def get_completed_run_by_fingerprint(self, quote_id: UUID, fingerprint: str) -> QuoteExtractionRun | None:
        model = self._session.scalars(
            select(QuoteExtractionRunModel)
            .where(
                QuoteExtractionRunModel.quote_id == quote_id,
                QuoteExtractionRunModel.extraction_fingerprint == fingerprint,
                QuoteExtractionRunModel.status == QuoteExtractionRunStatus.COMPLETED.value,
            )
            .order_by(QuoteExtractionRunModel.run_number.desc())
        ).first()
        return _run_from_model(model) if model else None

    def list_runs(self, quote_id: UUID) -> list[QuoteExtractionRun]:
        return [
            _run_from_model(model)
            for model in self._session.scalars(
                select(QuoteExtractionRunModel)
                .where(QuoteExtractionRunModel.quote_id == quote_id)
                .order_by(QuoteExtractionRunModel.run_number, QuoteExtractionRunModel.created_at)
            )
        ]

    def next_run_number(self, quote_id: UUID) -> int:
        value = self._session.scalar(
            select(func.max(QuoteExtractionRunModel.run_number)).where(
                QuoteExtractionRunModel.quote_id == quote_id
            )
        )
        return int(value or 0) + 1

    def supersede_current_items(self, quote_id: UUID) -> None:
        self._session.execute(
            update(QuoteItemModel)
            .where(QuoteItemModel.quote_id == quote_id, QuoteItemModel.is_current.is_(True))
            .values(is_current=False)
        )
        self._session.flush()

    def create_items(self, quote_id: UUID, items: tuple[QuoteItem, ...]) -> tuple[QuoteItem, ...]:
        models: list[QuoteItemModel] = []
        for item in items:
            model = QuoteItemModel(
                id=item.id,
                quote_id=quote_id,
                extraction_run_id=item.extraction_run_id,
                catalog_product_id=item.catalog_product_id,
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
                compliance_status=item.compliance_status.value,
                quoted_specifications=dict(item.quoted_specifications),
                match_status=item.match_status.value,
                match_score=item.match_score,
                match_reason=item.match_reason,
                warnings=list(item.warnings),
                notes=item.notes,
                source_evidence_id=item.source_evidence_id,
                source_page=item.source_page,
                evidence_fragment=item.evidence_fragment,
                confidence=item.confidence,
                original_extracted=dict(item.original_extracted),
                is_current=item.is_current,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            models.append(model)
        self._session.add_all(models)
        self._session.flush()
        return tuple(_item_from_model(model) for model in models)

    def replace_items(self, quote_id: UUID, items: tuple[QuoteItem, ...]) -> tuple[QuoteItem, ...]:
        # Backwards-compatible API. Historical rows are retained instead of deleted.
        self.supersede_current_items(quote_id)
        return self.create_items(quote_id, items)

    def list_items(self, quote_id: UUID) -> list[QuoteItem]:
        return [
            _item_from_model(model)
            for model in self._session.scalars(
                select(QuoteItemModel)
                .where(QuoteItemModel.quote_id == quote_id, QuoteItemModel.is_current.is_(True))
                .order_by(QuoteItemModel.created_at, QuoteItemModel.id)
            )
        ]

    def list_items_by_run(self, run_id: UUID) -> list[QuoteItem]:
        return [
            _item_from_model(model)
            for model in self._session.scalars(
                select(QuoteItemModel)
                .where(QuoteItemModel.extraction_run_id == run_id)
                .order_by(QuoteItemModel.created_at, QuoteItemModel.id)
            )
        ]

    def get_item(self, item_id: UUID, *, for_update: bool = False) -> QuoteItem | None:
        statement = select(QuoteItemModel).where(QuoteItemModel.id == item_id)
        if for_update:
            statement = statement.with_for_update()
        model = self._session.scalars(statement).first()
        return _item_from_model(model) if model else None

    def update_item(self, item: QuoteItem) -> QuoteItem:
        model = self._session.get(QuoteItemModel, item.id)
        if model is None:
            raise ValueError("Quote item does not exist.")
        model.catalog_product_id = item.catalog_product_id
        model.product_name = item.product_name
        model.description = item.description
        model.brand = item.brand
        model.model = item.model
        model.quantity = item.quantity
        model.unit = item.unit
        model.unit_price = item.unit_price
        model.total_price = item.total_price
        model.currency = item.currency
        model.delivery_days = item.delivery_days
        model.technical_compliance = item.technical_compliance
        model.compliance_status = item.compliance_status.value
        model.quoted_specifications = dict(item.quoted_specifications)
        model.match_status = item.match_status.value
        model.match_score = item.match_score
        model.match_reason = item.match_reason
        model.warnings = list(item.warnings)
        model.notes = item.notes
        model.source_evidence_id = item.source_evidence_id
        model.confidence = item.confidence
        model.is_current = item.is_current
        model.updated_at = item.updated_at
        self._session.flush()
        return _item_from_model(model)

    def create_evidence(self, evidence: QuoteEvidenceReference) -> QuoteEvidenceReference:
        model = QuoteEvidenceReferenceModel(
            id=evidence.id,
            quote_id=evidence.quote_id,
            quote_document_id=evidence.quote_document_id,
            extraction_run_id=evidence.extraction_run_id,
            entity_type=evidence.entity_type,
            entity_id=evidence.entity_id,
            field_name=evidence.field_name,
            locator_type=evidence.locator_type,
            locator=evidence.locator,
            fragment=evidence.fragment,
            extraction_method=evidence.extraction_method,
            finding_status=evidence.finding_status.value,
            confidence=evidence.confidence,
            created_at=evidence.created_at,
        )
        self._session.add(model)
        self._session.flush()
        return _evidence_from_model(model)

    def list_evidence(self, quote_id: UUID) -> list[QuoteEvidenceReference]:
        return [
            _evidence_from_model(model)
            for model in self._session.scalars(
                select(QuoteEvidenceReferenceModel)
                .where(QuoteEvidenceReferenceModel.quote_id == quote_id)
                .order_by(QuoteEvidenceReferenceModel.created_at, QuoteEvidenceReferenceModel.id)
            )
        ]

    def add_item_revision(self, revision: QuoteItemRevision) -> QuoteItemRevision:
        model = QuoteItemRevisionModel(
            id=revision.id,
            quote_id=revision.quote_id,
            quote_item_id=revision.quote_item_id,
            changed_by_user_id=revision.changed_by_user_id,
            before=dict(revision.before),
            after=dict(revision.after),
            changed_fields=list(revision.changed_fields),
            created_at=revision.created_at,
        )
        self._session.add(model)
        self._session.flush()
        return _revision_from_model(model)

    def list_item_revisions(self, quote_id: UUID) -> list[QuoteItemRevision]:
        return [
            _revision_from_model(model)
            for model in self._session.scalars(
                select(QuoteItemRevisionModel)
                .where(QuoteItemRevisionModel.quote_id == quote_id)
                .order_by(QuoteItemRevisionModel.created_at, QuoteItemRevisionModel.id)
            )
        ]

    def create_task(self, task: QuoteTaskRecord) -> QuoteTaskRecord:
        model = QuoteTaskRecordModel(
            id=task.id,
            quote_id=task.quote_id,
            correlation_id=task.correlation_id,
            task_name=task.task_name,
            status=task.status.value,
            attempt_count=task.attempt_count,
            force_reprocess=task.force_reprocess,
            last_error=task.last_error,
            queued_at=task.queued_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
            updated_at=task.updated_at,
        )
        self._session.add(model)
        self._session.flush()
        return _task_from_model(model)

    def update_task(self, task: QuoteTaskRecord) -> QuoteTaskRecord:
        model = self._session.get(QuoteTaskRecordModel, task.id)
        if model is None:
            raise ValueError("Quote task record does not exist.")
        model.status = task.status.value
        model.attempt_count = task.attempt_count
        model.force_reprocess = task.force_reprocess
        model.last_error = task.last_error
        model.started_at = task.started_at
        model.completed_at = task.completed_at
        model.updated_at = task.updated_at
        self._session.flush()
        return _task_from_model(model)

    def get_task(self, task_id: UUID, *, for_update: bool = False) -> QuoteTaskRecord | None:
        statement = select(QuoteTaskRecordModel).where(QuoteTaskRecordModel.id == task_id)
        if for_update:
            statement = statement.with_for_update()
        model = self._session.scalars(statement).first()
        return _task_from_model(model) if model else None

    def get_task_by_correlation(self, correlation_id: str) -> QuoteTaskRecord | None:
        model = self._session.scalars(
            select(QuoteTaskRecordModel).where(QuoteTaskRecordModel.correlation_id == correlation_id)
        ).first()
        return _task_from_model(model) if model else None

    def get_latest_task(self, quote_id: UUID) -> QuoteTaskRecord | None:
        model = self._session.scalars(
            select(QuoteTaskRecordModel)
            .where(QuoteTaskRecordModel.quote_id == quote_id)
            .order_by(QuoteTaskRecordModel.queued_at.desc())
        ).first()
        return _task_from_model(model) if model else None

    def create_comparison(self, comparison: ComparisonRun) -> ComparisonRun:
        model = ComparisonRunModel(
            id=comparison.id,
            tender_id=comparison.tender_id,
            catalog_snapshot_id=comparison.catalog_snapshot_id,
            comparison_key=comparison.comparison_key,
            approved_quotes_version=comparison.approved_quotes_version,
            scoring_config_version=comparison.scoring_config_version,
            rows=list(comparison.rows),
            recommendation=comparison.recommendation,
            generated_by_user_id=comparison.generated_by_user_id,
            created_at=comparison.created_at,
        )
        self._session.add(model)
        self._session.flush()
        return _comparison_from_model(model)

    def get_comparison_by_key(self, tender_id: UUID, key: str) -> ComparisonRun | None:
        model = self._session.scalars(
            select(ComparisonRunModel).where(
                ComparisonRunModel.tender_id == tender_id,
                ComparisonRunModel.comparison_key == key,
            )
        ).first()
        return _comparison_from_model(model) if model else None

    def get_latest_comparison(self, tender_id: UUID) -> ComparisonRun | None:
        model = self._session.scalars(
            select(ComparisonRunModel)
            .where(ComparisonRunModel.tender_id == tender_id)
            .order_by(ComparisonRunModel.created_at.desc())
        ).first()
        return _comparison_from_model(model) if model else None
