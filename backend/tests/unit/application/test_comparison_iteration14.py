from decimal import Decimal
from uuid import uuid4

from app.application.services.comparison_builder import (
    ApprovedQuoteSource,
    ComparisonBuilder,
    SupplierParticipant,
)
from app.application.services.comparison_normalization import ComparisonNormalizer
from app.domain.catalog.entities import CatalogSnapshot
from app.domain.comparison.entities import Comparison
from app.domain.comparison.value_objects import (
    ComparisonStatus,
    ComparisonWarningCode,
    MonetaryComparisonStatus,
    NormalizedCompliance,
    OfferStatus,
    QuantityComparisonStatus,
)
from app.domain.quotes.entities import Quote, QuoteItem
from app.domain.quotes.value_objects import ComplianceStatus, ProductMatchStatus, QuoteStatus


def _snapshot(products: tuple[dict, ...]) -> CatalogSnapshot:
    return CatalogSnapshot(
        tender_id=uuid4(),
        version=3,
        approved_by_user_id=uuid4(),
        products=products,
    )


def _comparison(snapshot: CatalogSnapshot) -> Comparison:
    return Comparison(
        tender_id=snapshot.tender_id,
        catalog_snapshot_id=snapshot.id,
        catalog_version=snapshot.version,
        quotes_version="a" * 64,
        comparison_version="1.0.0",
        comparison_key="b" * 64,
        created_by_user_id=uuid4(),
        source_quote_ids=(),
    )


def _quote(snapshot: CatalogSnapshot, supplier_id, *, currency: str | None = "MXN") -> Quote:
    quote = Quote(
        tender_id=snapshot.tender_id,
        tender_supplier_id=uuid4(),
        supplier_id=supplier_id,
        original_file_name="quote.pdf",
        storage_key="quotes/test.pdf",
        mime_type="application/pdf",
        file_size=100,
        file_hash="c" * 64,
        uploaded_by_user_id=uuid4(),
        currency=currency,
    )
    quote.status = QuoteStatus.APPROVED
    return quote


def _item(
    quote: Quote,
    product_id,
    *,
    quantity=Decimal("10"),
    unit="piece",
    price=Decimal("10"),
    currency="MXN",
    compliance=ComplianceStatus.COMPLIANT,
) -> QuoteItem:
    return QuoteItem(
        quote_id=quote.id,
        catalog_product_id=product_id,
        product_name="Router",
        quantity=quantity,
        unit=unit,
        unit_price=price,
        total_price=price * quantity if price is not None and quantity is not None else None,
        currency=currency,
        delivery_days=5,
        technical_compliance=None,
        compliance_status=compliance,
        match_status=ProductMatchStatus.MATCHED,
        match_score=1.0,
        confidence=0.95,
    )


def test_normalizer_does_not_convert_box_to_piece_and_unknown_stays_unknown() -> None:
    normalizer = ComparisonNormalizer()
    requested = normalizer.quantity(10, "piezas")
    quoted = normalizer.quantity(10, "caja")

    assert requested.unit == "piece"
    assert quoted.unit == "box"
    assert normalizer.compare_quantity(requested, quoted) is QuantityComparisonStatus.UNIT_MISMATCH
    assert normalizer.compliance(ComplianceStatus.UNKNOWN) is NormalizedCompliance.UNKNOWN


def test_builder_marks_missing_products_without_zero_price() -> None:
    product_a = uuid4()
    product_b = uuid4()
    snapshot = _snapshot(
        (
            {"product_id": str(product_a), "name": "Router", "quantity": "10", "unit": "piece"},
            {"product_id": str(product_b), "name": "Switch", "quantity": "5", "unit": "piece"},
        )
    )
    supplier_id = uuid4()
    quote = _quote(snapshot, supplier_id)
    result = ComparisonBuilder().build(
        _comparison(snapshot),
        snapshot,
        (SupplierParticipant(supplier_id, "Proveedor A"),),
        (ApprovedQuoteSource(supplier_id, "Proveedor A", quote, (_item(quote, product_a),)),),
    )

    assert result.status is ComparisonStatus.READY
    missing = result.items[1].offers[0]
    assert missing.status is OfferStatus.MISSING
    assert missing.unit_price.amount is None
    assert missing.total_price.amount is None
    assert {warning.code for warning in missing.warnings} == {
        ComparisonWarningCode.MISSING_PRODUCT_QUOTE
    }


def test_builder_flags_currency_mismatch_without_fx_conversion() -> None:
    product_id = uuid4()
    snapshot = _snapshot(
        ({"product_id": str(product_id), "name": "Router", "quantity": "10", "unit": "piece"},)
    )
    supplier_a = uuid4()
    supplier_b = uuid4()
    quote_a = _quote(snapshot, supplier_a, currency="MXN")
    quote_b = _quote(snapshot, supplier_b, currency="USD")
    result = ComparisonBuilder().build(
        _comparison(snapshot),
        snapshot,
        (
            SupplierParticipant(supplier_a, "Proveedor A"),
            SupplierParticipant(supplier_b, "Proveedor B"),
        ),
        (
            ApprovedQuoteSource(
                supplier_a,
                "Proveedor A",
                quote_a,
                (_item(quote_a, product_id, price=Decimal("100"), currency="MXN"),),
            ),
            ApprovedQuoteSource(
                supplier_b,
                "Proveedor B",
                quote_b,
                (_item(quote_b, product_id, price=Decimal("6"), currency="USD"),),
            ),
        ),
    )

    row = result.items[0]
    assert row.monetary_status is MonetaryComparisonStatus.REQUIRES_NORMALIZATION
    assert {offer.unit_price.currency for offer in row.offers} == {"MXN", "USD"}
    assert ComparisonWarningCode.CURRENCY_MISMATCH in {warning.code for warning in row.warnings}


def test_unknown_compliance_and_missing_delivery_are_warnings_not_compliance() -> None:
    product_id = uuid4()
    snapshot = _snapshot(
        ({"product_id": str(product_id), "name": "Router", "quantity": "10", "unit": "piece"},)
    )
    supplier_id = uuid4()
    quote = _quote(snapshot, supplier_id)
    item = _item(quote, product_id, compliance=ComplianceStatus.UNKNOWN)
    item.delivery_days = None
    quote.delivery_time_days = None

    result = ComparisonBuilder().build(
        _comparison(snapshot),
        snapshot,
        (SupplierParticipant(supplier_id, "Proveedor A"),),
        (ApprovedQuoteSource(supplier_id, "Proveedor A", quote, (item,)),),
    )

    offer = result.items[0].offers[0]
    codes = {warning.code for warning in offer.warnings}
    assert offer.compliance is NormalizedCompliance.UNKNOWN
    assert ComparisonWarningCode.COMPLIANCE_UNKNOWN in codes
    assert ComparisonWarningCode.DELIVERY_UNKNOWN in codes
    assert ComparisonWarningCode.INCOMPLETE_QUOTE in codes
    assert result.status is ComparisonStatus.READY


def test_duplicate_quote_item_is_critical_and_makes_comparison_invalid() -> None:
    product_id = uuid4()
    snapshot = _snapshot(
        ({"product_id": str(product_id), "name": "Router", "quantity": "10", "unit": "piece"},)
    )
    supplier_id = uuid4()
    quote = _quote(snapshot, supplier_id)
    first = _item(quote, product_id)
    second = _item(quote, product_id, price=Decimal("11"))

    result = ComparisonBuilder().build(
        _comparison(snapshot),
        snapshot,
        (SupplierParticipant(supplier_id, "Proveedor A"),),
        (ApprovedQuoteSource(supplier_id, "Proveedor A", quote, (first, second)),),
    )

    assert result.status is ComparisonStatus.INVALID
    offer = result.items[0].offers[0]
    assert offer.status is OfferStatus.INVALID
    assert ComparisonWarningCode.DUPLICATE_QUOTE_ITEM in {
        warning.code for warning in offer.warnings
    }


def test_product_outside_approved_snapshot_is_critical() -> None:
    product_id = uuid4()
    snapshot = _snapshot(
        ({"product_id": str(product_id), "name": "Router", "quantity": "10", "unit": "piece"},)
    )
    supplier_id = uuid4()
    quote = _quote(snapshot, supplier_id)
    alien = _item(quote, uuid4())

    result = ComparisonBuilder().build(
        _comparison(snapshot),
        snapshot,
        (SupplierParticipant(supplier_id, "Proveedor A"),),
        (ApprovedQuoteSource(supplier_id, "Proveedor A", quote, (alien,)),),
    )

    assert result.status is ComparisonStatus.INVALID
    assert ComparisonWarningCode.PRODUCT_UNIDENTIFIED in {
        warning.code for warning in result.warnings
    }
