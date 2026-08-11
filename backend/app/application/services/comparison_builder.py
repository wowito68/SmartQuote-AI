from dataclasses import dataclass
from uuid import UUID

from app.application.services.comparison_normalization import ComparisonNormalizer
from app.domain.catalog.entities import CatalogSnapshot
from app.domain.comparison.entities import (
    Comparison,
    ComparisonItem,
    ComparisonOffer,
    ComparisonWarning,
)
from app.domain.comparison.value_objects import (
    ComparisonWarningCode,
    MonetaryComparisonStatus,
    NormalizedCompliance,
    OfferStatus,
    Quantity,
    QuantityComparisonStatus,
    WarningSeverity,
)
from app.domain.quotes.entities import Quote, QuoteItem


@dataclass(frozen=True, slots=True)
class SupplierParticipant:
    supplier_id: UUID
    supplier_name: str


@dataclass(frozen=True, slots=True)
class ApprovedQuoteSource:
    supplier_id: UUID
    supplier_name: str
    quote: Quote
    items: tuple[QuoteItem, ...]


class ComparisonBuilder:
    """Build a deterministic comparison without scores or supplier recommendations."""

    def __init__(self, normalizer: ComparisonNormalizer | None = None) -> None:
        self._normalizer = normalizer or ComparisonNormalizer()

    @staticmethod
    def _warning(
        code: ComparisonWarningCode,
        message: str,
        *,
        severity: WarningSeverity = WarningSeverity.WARNING,
        supplier_id: UUID | None = None,
        quote_id: UUID | None = None,
        quote_item_id: UUID | None = None,
    ) -> ComparisonWarning:
        return ComparisonWarning(
            code=code,
            severity=severity,
            message=message,
            supplier_id=supplier_id,
            quote_id=quote_id,
            quote_item_id=quote_item_id,
        )

    def build(
        self,
        comparison: Comparison,
        snapshot: CatalogSnapshot,
        participants: tuple[SupplierParticipant, ...],
        quote_sources: tuple[ApprovedQuoteSource, ...],
    ) -> Comparison:
        comparison.start()
        global_warnings: list[ComparisonWarning] = []
        by_supplier: dict[UUID, list[ApprovedQuoteSource]] = {
            participant.supplier_id: [] for participant in participants
        }
        for source in quote_sources:
            by_supplier.setdefault(source.supplier_id, []).append(source)

        for participant in participants:
            sources = by_supplier.get(participant.supplier_id) or []
            if not sources:
                global_warnings.append(
                    self._warning(
                        ComparisonWarningCode.SUPPLIER_WITHOUT_VALID_QUOTE,
                        (
                            f"Supplier {participant.supplier_name} does not have "
                            "an approved quote."
                        ),
                        supplier_id=participant.supplier_id,
                    )
                )
            elif not any(source.items for source in sources):
                global_warnings.append(
                    self._warning(
                        ComparisonWarningCode.INCOMPLETE_QUOTE,
                        (
                            f"Supplier {participant.supplier_name} has an approved quote "
                            "without current quote items."
                        ),
                        supplier_id=participant.supplier_id,
                        quote_id=sources[-1].quote.id,
                    )
                )

        product_payloads: dict[UUID, dict] = {}
        for raw_product in snapshot.products:
            raw_id = raw_product.get("product_id") or raw_product.get("id")
            try:
                product_id = UUID(str(raw_id))
            except (TypeError, ValueError, AttributeError):
                continue
            product_payloads[product_id] = dict(raw_product)

        for source in quote_sources:
            for item in source.items:
                if (
                    item.catalog_product_id is None
                    or item.catalog_product_id not in product_payloads
                ):
                    global_warnings.append(
                        self._warning(
                            ComparisonWarningCode.PRODUCT_UNIDENTIFIED,
                            (
                                "An approved quote item cannot be associated with the "
                                "approved catalog snapshot."
                            ),
                            severity=WarningSeverity.CRITICAL,
                            supplier_id=source.supplier_id,
                            quote_id=source.quote.id,
                            quote_item_id=item.id,
                        )
                    )

        items: list[ComparisonItem] = []
        for product_id, raw_product in product_payloads.items():
            product_name = str(
                raw_product.get("name")
                or raw_product.get("product_name")
                or product_id
            )
            requested = self._normalizer.quantity(
                raw_product.get("quantity"),
                raw_product.get("unit"),
            )
            item_warnings: list[ComparisonWarning] = []
            if requested.value is None:
                item_warnings.append(
                    self._warning(
                        ComparisonWarningCode.REQUESTED_QUANTITY_UNKNOWN,
                        f"Requested quantity is unknown for {product_name}.",
                    )
                )
            if requested.unit is None:
                item_warnings.append(
                    self._warning(
                        ComparisonWarningCode.REQUESTED_UNIT_UNKNOWN,
                        f"Requested unit is unknown for {product_name}.",
                    )
                )

            offers: list[ComparisonOffer] = []
            for participant in participants:
                sources = by_supplier.get(participant.supplier_id, [])
                matches: list[tuple[ApprovedQuoteSource, QuoteItem]] = []
                for source in sources:
                    matches.extend(
                        (source, quote_item)
                        for quote_item in source.items
                        if quote_item.catalog_product_id == product_id
                    )

                if not matches:
                    quote_id = sources[-1].quote.id if sources else None
                    warning = self._warning(
                        ComparisonWarningCode.MISSING_PRODUCT_QUOTE,
                        (
                            f"Supplier {participant.supplier_name} did not quote "
                            f"{product_name}."
                        ),
                        supplier_id=participant.supplier_id,
                        quote_id=quote_id,
                    )
                    offers.append(
                        ComparisonOffer(
                            supplier_id=participant.supplier_id,
                            supplier_name=participant.supplier_name,
                            status=OfferStatus.MISSING,
                            quote_id=quote_id,
                            warnings=(warning,),
                        )
                    )
                    continue

                if len(matches) > 1:
                    duplicate_warning = self._warning(
                        ComparisonWarningCode.DUPLICATE_QUOTE_ITEM,
                        (
                            f"Supplier {participant.supplier_name} has multiple "
                            f"approved quote items for {product_name}."
                        ),
                        severity=WarningSeverity.CRITICAL,
                        supplier_id=participant.supplier_id,
                        quote_id=matches[0][0].quote.id,
                    )
                    offers.append(
                        ComparisonOffer(
                            supplier_id=participant.supplier_id,
                            supplier_name=participant.supplier_name,
                            status=OfferStatus.INVALID,
                            quote_id=matches[0][0].quote.id,
                            warnings=(duplicate_warning,),
                        )
                    )
                    continue

                source, quote_item = matches[0]
                offers.append(
                    self._build_offer(
                        participant,
                        source.quote,
                        quote_item,
                        requested,
                    )
                )

            currencies = {
                offer.unit_price.currency or offer.total_price.currency
                for offer in offers
                if offer.status is OfferStatus.QUOTED
                and (
                    offer.unit_price.amount is not None
                    or offer.total_price.amount is not None
                )
                and (offer.unit_price.currency or offer.total_price.currency)
            }
            complete_prices = [
                offer
                for offer in offers
                if offer.status is OfferStatus.QUOTED
                and (
                    offer.unit_price.amount is not None
                    or offer.total_price.amount is not None
                )
                and (offer.unit_price.currency or offer.total_price.currency)
            ]
            if len(currencies) > 1:
                monetary_status = MonetaryComparisonStatus.REQUIRES_NORMALIZATION
                item_warnings.append(
                    self._warning(
                        ComparisonWarningCode.CURRENCY_MISMATCH,
                        (
                            f"Quoted prices for {product_name} use multiple currencies; "
                            "no FX conversion was applied."
                        ),
                    )
                )
            elif len(complete_prices) >= 2:
                monetary_status = MonetaryComparisonStatus.COMPARABLE
            else:
                monetary_status = MonetaryComparisonStatus.INSUFFICIENT_DATA

            items.append(
                ComparisonItem(
                    comparison_id=comparison.id,
                    product_id=product_id,
                    requested_product_name=product_name,
                    requested_quantity=requested,
                    offers=tuple(offers),
                    monetary_status=monetary_status,
                    warnings=tuple(item_warnings),
                )
            )

        comparison.complete(tuple(items), tuple(global_warnings))
        return comparison

    def _build_offer(
        self,
        participant: SupplierParticipant,
        quote: Quote,
        item: QuoteItem,
        requested: Quantity,
    ) -> ComparisonOffer:
        warnings: list[ComparisonWarning] = []
        quoted_quantity = self._normalizer.quantity(item.quantity, item.unit)
        quantity_status = self._normalizer.compare_quantity(requested, quoted_quantity)
        if quantity_status is QuantityComparisonStatus.QUANTITY_MISMATCH:
            warnings.append(
                self._warning(
                    ComparisonWarningCode.QUANTITY_MISMATCH,
                    "Quoted quantity differs from the requested quantity.",
                    supplier_id=participant.supplier_id,
                    quote_id=quote.id,
                    quote_item_id=item.id,
                )
            )
        elif quantity_status is QuantityComparisonStatus.UNIT_MISMATCH:
            warnings.append(
                self._warning(
                    ComparisonWarningCode.UNIT_MISMATCH,
                    (
                        "Quoted unit differs from the requested unit; "
                        "no conversion was assumed."
                    ),
                    supplier_id=participant.supplier_id,
                    quote_id=quote.id,
                    quote_item_id=item.id,
                )
            )

        currency = item.currency or quote.currency
        unit_price = self._normalizer.money(item.unit_price, currency)
        total_price = self._normalizer.money(item.total_price, currency)
        if item.unit_price is None and item.total_price is None:
            warnings.append(
                self._warning(
                    ComparisonWarningCode.MISSING_PRICE,
                    "Quoted item does not contain a usable price.",
                    supplier_id=participant.supplier_id,
                    quote_id=quote.id,
                    quote_item_id=item.id,
                )
            )
        if currency is None and (
            item.unit_price is not None or item.total_price is not None
        ):
            warnings.append(
                self._warning(
                    ComparisonWarningCode.MISSING_CURRENCY,
                    "Quoted price does not have an explicit currency.",
                    supplier_id=participant.supplier_id,
                    quote_id=quote.id,
                    quote_item_id=item.id,
                )
            )

        compliance = self._normalizer.compliance(item.compliance_status)
        if compliance is NormalizedCompliance.UNKNOWN:
            warnings.append(
                self._warning(
                    ComparisonWarningCode.COMPLIANCE_UNKNOWN,
                    "Technical compliance is unknown and was not interpreted as compliant.",
                    supplier_id=participant.supplier_id,
                    quote_id=quote.id,
                    quote_item_id=item.id,
                )
            )

        delivery = self._normalizer.delivery(item, quote.delivery_time_days)
        if not delivery.is_known:
            warnings.append(
                self._warning(
                    ComparisonWarningCode.DELIVERY_UNKNOWN,
                    "Delivery time is unknown.",
                    supplier_id=participant.supplier_id,
                    quote_id=quote.id,
                    quote_item_id=item.id,
                )
            )
        elif not delivery.normalized:
            warnings.append(
                self._warning(
                    ComparisonWarningCode.DELIVERY_NOT_NORMALIZED,
                    "Delivery time is only available as ambiguous source text.",
                    supplier_id=participant.supplier_id,
                    quote_id=quote.id,
                    quote_item_id=item.id,
                )
            )

        incomplete_codes = {
            ComparisonWarningCode.MISSING_PRICE,
            ComparisonWarningCode.MISSING_CURRENCY,
            ComparisonWarningCode.COMPLIANCE_UNKNOWN,
            ComparisonWarningCode.DELIVERY_UNKNOWN,
        }
        if any(warning.code in incomplete_codes for warning in warnings):
            warnings.append(
                self._warning(
                    ComparisonWarningCode.INCOMPLETE_QUOTE,
                    (
                        "Quoted product has incomplete fields for one or more "
                        "comparison dimensions."
                    ),
                    supplier_id=participant.supplier_id,
                    quote_id=quote.id,
                    quote_item_id=item.id,
                )
            )

        return ComparisonOffer(
            supplier_id=participant.supplier_id,
            supplier_name=participant.supplier_name,
            status=OfferStatus.QUOTED,
            quote_id=quote.id,
            quote_item_id=item.id,
            quoted_product_name=item.product_name,
            brand=item.brand,
            model=item.model,
            quantity=quoted_quantity,
            quantity_status=quantity_status,
            unit_price=unit_price,
            total_price=total_price,
            compliance=compliance,
            delivery=delivery,
            observations=item.notes,
            commercial_terms=quote.commercial_terms,
            evidence_id=item.source_evidence_id,
            confidence=item.confidence,
            warnings=tuple(warnings),
        )
