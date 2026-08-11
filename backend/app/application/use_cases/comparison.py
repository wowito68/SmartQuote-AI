import hashlib
import json
from uuid import UUID

from app.application.dtos.comparison import (
    ComparisonItemResponse,
    ComparisonOfferResponse,
    ComparisonResponse,
    ComparisonWarningResponse,
)
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.application.services.comparison_builder import (
    ApprovedQuoteSource,
    ComparisonBuilder,
    SupplierParticipant,
)
from app.domain.comparison.entities import Comparison, ComparisonWarning
from app.domain.comparison.exceptions import ComparisonNotFound, ComparisonNotReady
from app.domain.comparison.value_objects import ComparisonStatus
from app.domain.quotes.events import quote_event
from app.domain.quotes.value_objects import QuoteStatus
from app.domain.suppliers.value_objects import SupplierStatus
from app.domain.tenders.value_objects import TenderStatus


def _warning_response(warning: ComparisonWarning) -> ComparisonWarningResponse:
    return ComparisonWarningResponse(
        code=warning.code.value,
        severity=warning.severity,
        message=warning.message,
        supplier_id=warning.supplier_id,
        quote_id=warning.quote_id,
        quote_item_id=warning.quote_item_id,
    )


def _comparison_response(comparison: Comparison) -> ComparisonResponse:
    return ComparisonResponse(
        id=comparison.id,
        tender_id=comparison.tender_id,
        catalog_snapshot_id=comparison.catalog_snapshot_id,
        catalog_version=comparison.catalog_version,
        quotes_version=comparison.quotes_version,
        comparison_version=comparison.comparison_version,
        comparison_key=comparison.comparison_key,
        status=comparison.status,
        created_by_user_id=comparison.created_by_user_id,
        source_quote_ids=comparison.source_quote_ids,
        items=tuple(
            ComparisonItemResponse(
                id=item.id,
                product_id=item.product_id,
                requested_product=item.requested_product_name,
                requested_quantity=item.requested_quantity.value,
                requested_unit=item.requested_quantity.unit,
                monetary_status=item.monetary_status,
                offers=tuple(
                    ComparisonOfferResponse(
                        id=offer.id,
                        supplier_id=offer.supplier_id,
                        supplier_name=offer.supplier_name,
                        status=offer.status,
                        quote_id=offer.quote_id,
                        quote_item_id=offer.quote_item_id,
                        quoted_product_name=offer.quoted_product_name,
                        brand=offer.brand,
                        model=offer.model,
                        quantity=offer.quantity.value,
                        unit=offer.quantity.unit,
                        quantity_status=offer.quantity_status,
                        unit_price=offer.unit_price.amount,
                        total_price=offer.total_price.amount,
                        currency=offer.unit_price.currency or offer.total_price.currency,
                        compliance=offer.compliance,
                        delivery_days=offer.delivery.days,
                        delivery_original_text=offer.delivery.original_text,
                        delivery_normalized=offer.delivery.normalized,
                        observations=offer.observations,
                        commercial_terms=offer.commercial_terms,
                        evidence_id=offer.evidence_id,
                        confidence=offer.confidence,
                        warnings=tuple(
                            _warning_response(warning) for warning in offer.warnings
                        ),
                    )
                    for offer in item.offers
                ),
                warnings=tuple(_warning_response(warning) for warning in item.warnings),
            )
            for item in comparison.items
        ),
        warnings=tuple(_warning_response(warning) for warning in comparison.warnings),
        created_at=comparison.created_at,
        completed_at=comparison.completed_at,
    )


def _approved_quotes_version(quotes) -> str:
    payload = [
        {
            "id": str(quote.id),
            "version": quote.version,
            "file_hash": quote.file_hash,
            "approved_extraction_run_id": (
                str(quote.approved_extraction_run_id)
                if quote.approved_extraction_run_id
                else None
            ),
        }
        for quote in sorted(quotes, key=lambda item: str(item.id))
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _comparison_key(
    tender_id: UUID,
    catalog_snapshot_id: UUID,
    catalog_version: int,
    quotes_version: str,
    rules_version: str,
) -> str:
    payload = "|".join(
        (
            str(tender_id),
            f"{catalog_snapshot_id}:{catalog_version}",
            quotes_version,
            rules_version,
        )
    )
    return hashlib.sha256(payload.encode()).hexdigest()


class GenerateTenderComparison:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        builder: ComparisonBuilder,
        *,
        comparison_rules_version: str,
    ) -> None:
        self._uow_factory = uow_factory
        self._builder = builder
        self._rules_version = comparison_rules_version

    def execute(self, tender_id: UUID, created_by_user_id: UUID) -> ComparisonResponse:
        with self._uow_factory() as uow:
            tender = uow.tenders.get_by_id(tender_id)
            if tender is None:
                from app.application.exceptions import TenderNotFound

                raise TenderNotFound("Tender was not found.")
            if not uow.users.exists(created_by_user_id):
                raise ComparisonNotReady("Comparison creator user does not exist.")
            snapshot = uow.catalogs.get_latest_snapshot(tender_id)
            if snapshot is None:
                raise ComparisonNotReady("Comparison requires an approved catalog snapshot.")

            quotes = uow.quotes.list_quotes_by_status(
                tender_id,
                {QuoteStatus.APPROVED, QuoteStatus.INCLUDED_IN_COMPARISON},
            )
            if not quotes:
                raise ComparisonNotReady("Comparison requires at least one approved quote.")

            quotes_version = _approved_quotes_version(quotes)
            key = _comparison_key(
                tender_id,
                snapshot.id,
                snapshot.version,
                quotes_version,
                self._rules_version,
            )
            existing = uow.comparisons.get_by_key(tender_id, key)
            if existing is not None:
                return _comparison_response(existing)

            participant_by_supplier: dict[UUID, SupplierParticipant] = {}
            participant_statuses = {
                SupplierStatus.APPROVED,
                SupplierStatus.CONTACTED,
                SupplierStatus.RESPONDED,
            }
            for tender_supplier in uow.suppliers.list_tender_suppliers(tender_id):
                if tender_supplier.status not in participant_statuses:
                    continue
                supplier = uow.suppliers.get_supplier(tender_supplier.supplier_id)
                if supplier is None:
                    continue
                participant_by_supplier[supplier.id] = SupplierParticipant(
                    supplier_id=supplier.id,
                    supplier_name=supplier.display_name,
                )

            sources: list[ApprovedQuoteSource] = []
            for quote in quotes:
                supplier = uow.suppliers.get_supplier(quote.supplier_id)
                if supplier is None:
                    raise ComparisonNotReady(
                        f"Approved quote {quote.id} references a missing supplier."
                    )
                participant_by_supplier.setdefault(
                    supplier.id,
                    SupplierParticipant(
                        supplier_id=supplier.id,
                        supplier_name=supplier.display_name,
                    ),
                )
                sources.append(
                    ApprovedQuoteSource(
                        supplier_id=supplier.id,
                        supplier_name=supplier.display_name,
                        quote=quote,
                        items=tuple(uow.quotes.list_items(quote.id)),
                    )
                )

            comparison = Comparison(
                tender_id=tender_id,
                catalog_snapshot_id=snapshot.id,
                catalog_version=snapshot.version,
                quotes_version=quotes_version,
                comparison_version=self._rules_version,
                comparison_key=key,
                created_by_user_id=created_by_user_id,
                source_quote_ids=tuple(
                    quote.id for quote in sorted(quotes, key=lambda item: str(item.id))
                ),
            )
            comparison = self._builder.build(
                comparison,
                snapshot,
                tuple(
                    sorted(
                        participant_by_supplier.values(),
                        key=lambda item: (item.supplier_name.casefold(), str(item.supplier_id)),
                    )
                ),
                tuple(sources),
            )
            stored = uow.comparisons.create(comparison)

            if stored.status is ComparisonStatus.READY and tender.status is TenderStatus.QUOTE_ANALYSIS:
                tender.change_status(TenderStatus.COMPARISON_READY)
                uow.tenders.update(tender)

            event_name = (
                "comparison.ready"
                if stored.status is ComparisonStatus.READY
                else "comparison.invalid"
            )
            uow.audit_events.append(
                quote_event(
                    stored.id,
                    "comparison.created",
                    aggregate_type="comparison",
                    tender_id=str(tender_id),
                    catalog_snapshot_id=str(snapshot.id),
                    catalog_version=snapshot.version,
                    quotes_version=quotes_version,
                    comparison_version=self._rules_version,
                    comparison_key=key,
                    source_quote_ids=[str(value) for value in stored.source_quote_ids],
                    item_count=len(stored.items),
                    status=stored.status.value,
                )
            )
            uow.audit_events.append(
                quote_event(
                    stored.id,
                    event_name,
                    aggregate_type="comparison",
                    tender_id=str(tender_id),
                    warning_count=(
                        len(stored.warnings)
                        + sum(len(item.warnings) for item in stored.items)
                        + sum(
                            len(offer.warnings)
                            for item in stored.items
                            for offer in item.offers
                        )
                    ),
                )
            )
            uow.commit()
            return _comparison_response(stored)


class GetTenderComparison:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, tender_id: UUID) -> ComparisonResponse:
        with self._uow_factory() as uow:
            comparison = uow.comparisons.get_latest(tender_id)
            if comparison is None:
                raise ComparisonNotFound("Tender comparison was not found.")
            return _comparison_response(comparison)


class GetComparison:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, comparison_id: UUID) -> ComparisonResponse:
        with self._uow_factory() as uow:
            comparison = uow.comparisons.get(comparison_id)
            if comparison is None:
                raise ComparisonNotFound("Comparison was not found.")
            return _comparison_response(comparison)
