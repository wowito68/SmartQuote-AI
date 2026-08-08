from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.application.ports.quote_repository import QuoteRepository
from app.domain.comparisons.entities import ComparisonRun
from app.domain.quotes.entities import Quote, QuoteExtractionRun, QuoteItem
from app.domain.quotes.value_objects import QuoteExtractionRunStatus, QuoteStatus
from app.infrastructure.db.models.quote import (
    ComparisonRunModel,
    QuoteExtractionRunModel,
    QuoteItemModel,
    QuoteModel,
)


def _quote_from_model(model: QuoteModel) -> Quote:
    return Quote(
        id=model.id,
        tender_id=model.tender_id,
        tender_supplier_id=model.tender_supplier_id,
        supplier_id=model.supplier_id,
        original_file_name=model.original_file_name,
        storage_key=model.storage_key,
        mime_type=model.mime_type,
        file_size=model.file_size,
        file_hash=model.file_hash,
        uploaded_by_user_id=model.uploaded_by_user_id,
        status=QuoteStatus(model.status),
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
    model.status = quote.status.value
    model.version = quote.version
    model.manual_edit_count = quote.manual_edit_count
    model.reviewed_by_user_id = quote.reviewed_by_user_id
    model.reviewed_at = quote.reviewed_at
    model.rejection_reason = quote.rejection_reason
    model.last_error = quote.last_error
    model.updated_at = quote.updated_at


def _run_from_model(model: QuoteExtractionRunModel) -> QuoteExtractionRun:
    return QuoteExtractionRun(
        id=model.id,
        quote_id=model.quote_id,
        tender_id=model.tender_id,
        supplier_id=model.supplier_id,
        idempotency_key=model.idempotency_key,
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
        raw_response=model.raw_response,
        error_type=model.error_type,
        error_message=model.error_message,
        started_at=model.started_at,
        completed_at=model.completed_at,
        created_at=model.created_at,
    )


def _item_from_model(model: QuoteItemModel) -> QuoteItem:
    return QuoteItem(
        id=model.id,
        quote_id=model.quote_id,
        catalog_product_id=model.catalog_product_id,
        product_name=model.product_name,
        brand=model.brand,
        model=model.model,
        quantity=model.quantity,
        unit_price=model.unit_price,
        total_price=model.total_price,
        currency=model.currency,
        delivery_days=model.delivery_days,
        technical_compliance=model.technical_compliance,
        notes=model.notes,
        source_page=model.source_page,
        evidence_fragment=model.evidence_fragment,
        confidence=model.confidence,
        created_at=model.created_at,
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
            original_file_name=quote.original_file_name,
            storage_key=quote.storage_key,
            mime_type=quote.mime_type,
            file_size=quote.file_size,
            file_hash=quote.file_hash,
            uploaded_by_user_id=quote.uploaded_by_user_id,
            status=quote.status.value,
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
        statement = select(QuoteModel).where(
            QuoteModel.tender_id == tender_id,
            QuoteModel.supplier_id == supplier_id,
            QuoteModel.file_hash == file_hash,
        )
        model = self._session.scalars(statement).first()
        return _quote_from_model(model) if model else None

    def list_quotes(self, tender_id: UUID) -> list[Quote]:
        statement = (
            select(QuoteModel)
            .where(QuoteModel.tender_id == tender_id)
            .order_by(QuoteModel.created_at, QuoteModel.id)
        )
        return [_quote_from_model(model) for model in self._session.scalars(statement)]

    def list_quotes_by_status(self, tender_id: UUID, statuses: set[QuoteStatus]) -> list[Quote]:
        statement = select(QuoteModel).where(
            QuoteModel.tender_id == tender_id,
            QuoteModel.status.in_([status.value for status in statuses]),
        )
        return [_quote_from_model(model) for model in self._session.scalars(statement)]

    def create_run(self, run: QuoteExtractionRun) -> QuoteExtractionRun:
        model = QuoteExtractionRunModel(
            id=run.id,
            quote_id=run.quote_id,
            tender_id=run.tender_id,
            supplier_id=run.supplier_id,
            idempotency_key=run.idempotency_key,
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
            raw_response=run.raw_response,
            error_type=run.error_type,
            error_message=run.error_message,
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
        model.raw_response = run.raw_response
        model.error_type = run.error_type
        model.error_message = run.error_message
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
        statement = select(QuoteExtractionRunModel).where(
            QuoteExtractionRunModel.quote_id == quote_id,
            QuoteExtractionRunModel.idempotency_key == key,
        )
        model = self._session.scalars(statement).first()
        return _run_from_model(model) if model else None

    def replace_items(self, quote_id: UUID, items: tuple[QuoteItem, ...]) -> tuple[QuoteItem, ...]:
        self._session.execute(delete(QuoteItemModel).where(QuoteItemModel.quote_id == quote_id))
        models = [
            QuoteItemModel(
                id=item.id,
                quote_id=quote_id,
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
                created_at=item.created_at,
            )
            for item in items
        ]
        self._session.add_all(models)
        self._session.flush()
        return tuple(_item_from_model(model) for model in models)

    def list_items(self, quote_id: UUID) -> list[QuoteItem]:
        statement = (
            select(QuoteItemModel)
            .where(QuoteItemModel.quote_id == quote_id)
            .order_by(QuoteItemModel.created_at, QuoteItemModel.id)
        )
        return [_item_from_model(model) for model in self._session.scalars(statement)]

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
        statement = select(ComparisonRunModel).where(
            ComparisonRunModel.tender_id == tender_id,
            ComparisonRunModel.comparison_key == key,
        )
        model = self._session.scalars(statement).first()
        return _comparison_from_model(model) if model else None

    def get_latest_comparison(self, tender_id: UUID) -> ComparisonRun | None:
        statement = (
            select(ComparisonRunModel)
            .where(ComparisonRunModel.tender_id == tender_id)
            .order_by(ComparisonRunModel.created_at.desc())
        )
        model = self._session.scalars(statement).first()
        return _comparison_from_model(model) if model else None
