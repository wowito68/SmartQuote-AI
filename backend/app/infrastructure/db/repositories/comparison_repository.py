from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.ports.comparison_repository import ComparisonRepository
from app.domain.comparison.entities import (
    Comparison,
    ComparisonItem,
    ComparisonOffer,
    ComparisonWarning,
)
from app.domain.comparison.value_objects import (
    ComparisonStatus,
    ComparisonWarningCode,
    DeliveryTime,
    Money,
    MonetaryComparisonStatus,
    NormalizedCompliance,
    OfferStatus,
    Quantity,
    QuantityComparisonStatus,
    WarningSeverity,
)
from app.infrastructure.db.models.comparison import (
    ComparisonItemModel,
    ComparisonModel,
    ComparisonOfferModel,
)


def _warning_to_dict(warning: ComparisonWarning) -> dict:
    return warning.as_dict()


def _warning_from_dict(payload: dict) -> ComparisonWarning:
    return ComparisonWarning(
        code=ComparisonWarningCode(payload["code"]),
        severity=WarningSeverity(payload["severity"]),
        message=str(payload["message"]),
        supplier_id=UUID(payload["supplier_id"]) if payload.get("supplier_id") else None,
        quote_id=UUID(payload["quote_id"]) if payload.get("quote_id") else None,
        quote_item_id=(
            UUID(payload["quote_item_id"]) if payload.get("quote_item_id") else None
        ),
    )


class SqlAlchemyComparisonRepository(ComparisonRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, comparison: Comparison) -> Comparison:
        model = ComparisonModel(
            id=comparison.id,
            tender_id=comparison.tender_id,
            catalog_snapshot_id=comparison.catalog_snapshot_id,
            catalog_version=comparison.catalog_version,
            quotes_version=comparison.quotes_version,
            comparison_version=comparison.comparison_version,
            comparison_key=comparison.comparison_key,
            status=comparison.status.value,
            created_by_user_id=comparison.created_by_user_id,
            source_quote_ids=[str(value) for value in comparison.source_quote_ids],
            warnings=[_warning_to_dict(value) for value in comparison.warnings],
            created_at=comparison.created_at,
            completed_at=comparison.completed_at,
        )
        self._session.add(model)
        self._session.flush()
        for item in comparison.items:
            item_model = ComparisonItemModel(
                id=item.id,
                comparison_id=comparison.id,
                product_id=item.product_id,
                requested_product_name=item.requested_product_name,
                requested_quantity=item.requested_quantity.value,
                requested_unit=item.requested_quantity.unit,
                monetary_status=item.monetary_status.value,
                warnings=[_warning_to_dict(value) for value in item.warnings],
                created_at=item.created_at,
            )
            self._session.add(item_model)
            for offer in item.offers:
                currency = offer.unit_price.currency or offer.total_price.currency
                self._session.add(
                    ComparisonOfferModel(
                        id=offer.id,
                        comparison_item_id=item.id,
                        supplier_id=offer.supplier_id,
                        supplier_name=offer.supplier_name,
                        quote_id=offer.quote_id,
                        quote_item_id=offer.quote_item_id,
                        status=offer.status.value,
                        quoted_product_name=offer.quoted_product_name,
                        brand=offer.brand,
                        model=offer.model,
                        quoted_quantity=offer.quantity.value,
                        quoted_unit=offer.quantity.unit,
                        quantity_status=offer.quantity_status.value,
                        unit_price=offer.unit_price.amount,
                        total_price=offer.total_price.amount,
                        currency=currency,
                        compliance_status=offer.compliance.value,
                        delivery_days=offer.delivery.days,
                        delivery_original_text=offer.delivery.original_text,
                        delivery_normalized=offer.delivery.normalized,
                        observations=offer.observations,
                        commercial_terms=offer.commercial_terms,
                        evidence_id=offer.evidence_id,
                        confidence=offer.confidence,
                        warnings=[_warning_to_dict(value) for value in offer.warnings],
                    )
                )
        self._session.flush()
        return self.get(comparison.id) or comparison

    def get(self, comparison_id: UUID) -> Comparison | None:
        model = self._session.get(ComparisonModel, comparison_id)
        return self._hydrate(model) if model else None

    def get_by_key(self, tender_id: UUID, comparison_key: str) -> Comparison | None:
        model = self._session.scalars(
            select(ComparisonModel).where(
                ComparisonModel.tender_id == tender_id,
                ComparisonModel.comparison_key == comparison_key,
            )
        ).first()
        return self._hydrate(model) if model else None

    def get_latest(self, tender_id: UUID) -> Comparison | None:
        model = self._session.scalars(
            select(ComparisonModel)
            .where(ComparisonModel.tender_id == tender_id)
            .order_by(ComparisonModel.created_at.desc(), ComparisonModel.id.desc())
        ).first()
        return self._hydrate(model) if model else None

    def _hydrate(self, model: ComparisonModel) -> Comparison:
        item_models = list(
            self._session.scalars(
                select(ComparisonItemModel)
                .where(ComparisonItemModel.comparison_id == model.id)
                .order_by(ComparisonItemModel.created_at, ComparisonItemModel.id)
            )
        )
        item_ids = [item.id for item in item_models]
        offer_models = (
            list(
                self._session.scalars(
                    select(ComparisonOfferModel)
                    .where(ComparisonOfferModel.comparison_item_id.in_(item_ids))
                    .order_by(
                        ComparisonOfferModel.comparison_item_id,
                        ComparisonOfferModel.supplier_name,
                        ComparisonOfferModel.id,
                    )
                )
            )
            if item_ids
            else []
        )
        offers_by_item: dict[UUID, list[ComparisonOffer]] = {item_id: [] for item_id in item_ids}
        for offer in offer_models:
            currency = offer.currency
            offers_by_item[offer.comparison_item_id].append(
                ComparisonOffer(
                    id=offer.id,
                    supplier_id=offer.supplier_id,
                    supplier_name=offer.supplier_name,
                    status=OfferStatus(offer.status),
                    quote_id=offer.quote_id,
                    quote_item_id=offer.quote_item_id,
                    quoted_product_name=offer.quoted_product_name,
                    brand=offer.brand,
                    model=offer.model,
                    quantity=Quantity(offer.quoted_quantity, offer.quoted_unit),
                    quantity_status=QuantityComparisonStatus(offer.quantity_status),
                    unit_price=Money(offer.unit_price, currency),
                    total_price=Money(offer.total_price, currency),
                    compliance=NormalizedCompliance(offer.compliance_status),
                    delivery=DeliveryTime(
                        offer.delivery_days,
                        offer.delivery_original_text,
                        offer.delivery_normalized,
                    ),
                    observations=offer.observations,
                    commercial_terms=offer.commercial_terms,
                    evidence_id=offer.evidence_id,
                    confidence=offer.confidence,
                    warnings=tuple(_warning_from_dict(value) for value in offer.warnings),
                )
            )
        items = tuple(
            ComparisonItem(
                id=item.id,
                comparison_id=model.id,
                product_id=item.product_id,
                requested_product_name=item.requested_product_name,
                requested_quantity=Quantity(item.requested_quantity, item.requested_unit),
                offers=tuple(offers_by_item[item.id]),
                monetary_status=MonetaryComparisonStatus(item.monetary_status),
                warnings=tuple(_warning_from_dict(value) for value in item.warnings),
                created_at=item.created_at,
            )
            for item in item_models
        )
        return Comparison(
            id=model.id,
            tender_id=model.tender_id,
            catalog_snapshot_id=model.catalog_snapshot_id,
            catalog_version=model.catalog_version,
            quotes_version=model.quotes_version,
            comparison_version=model.comparison_version,
            comparison_key=model.comparison_key,
            created_by_user_id=model.created_by_user_id,
            source_quote_ids=tuple(UUID(value) for value in model.source_quote_ids),
            status=ComparisonStatus(model.status),
            items=items,
            warnings=tuple(_warning_from_dict(value) for value in model.warnings),
            created_at=model.created_at,
            completed_at=model.completed_at,
        )
