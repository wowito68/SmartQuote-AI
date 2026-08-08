from datetime import UTC, datetime

from app.domain.catalog.entities import CatalogProduct
from app.domain.catalog.exceptions import InvalidProductState
from app.domain.catalog.value_objects import ProductStatus
from app.domain.rfqs.entities import RfqRequest
from app.domain.rfqs.exceptions import InvalidRfqState
from app.domain.rfqs.value_objects import RfqStatus
from app.domain.suppliers.entities import TenderSupplier
from app.domain.suppliers.exceptions import InvalidSupplierState
from app.domain.suppliers.value_objects import SupplierStatus


def mark_supplier_contacted(item: TenderSupplier) -> None:
    if item.status is SupplierStatus.CONTACTED:
        return
    if item.status is not SupplierStatus.APPROVED:
        raise InvalidSupplierState("Only approved suppliers can be marked as contacted.")
    item.status = SupplierStatus.CONTACTED
    item.updated_at = datetime.now(UTC)


def mark_supplier_responded(item: TenderSupplier) -> None:
    if item.status is SupplierStatus.RESPONDED:
        return
    if item.status is SupplierStatus.APPROVED:
        mark_supplier_contacted(item)
    if item.status is not SupplierStatus.CONTACTED:
        raise InvalidSupplierState("Only contacted suppliers can be marked as responded.")
    item.status = SupplierStatus.RESPONDED
    item.updated_at = datetime.now(UTC)


def mark_rfq_responded(rfq: RfqRequest) -> None:
    if rfq.status is RfqStatus.RESPONDED:
        return
    if rfq.status not in {RfqStatus.SENT, RfqStatus.DELIVERED}:
        raise InvalidRfqState("Only sent RFQs can be marked as responded.")
    rfq.status = RfqStatus.RESPONDED
    rfq.updated_at = datetime.now(UTC)


def mark_product_quoted(product: CatalogProduct) -> None:
    if product.status in {ProductStatus.QUOTED, ProductStatus.COMPARED}:
        return
    if product.status is not ProductStatus.APPROVED:
        raise InvalidProductState("Only approved products can be marked as quoted.")
    product.status = ProductStatus.QUOTED
    product.updated_at = datetime.now(UTC)


def mark_product_compared(product: CatalogProduct) -> None:
    if product.status is ProductStatus.COMPARED:
        return
    if product.status is ProductStatus.APPROVED:
        mark_product_quoted(product)
    if product.status is not ProductStatus.QUOTED:
        raise InvalidProductState("Only quoted products can be marked as compared.")
    product.status = ProductStatus.COMPARED
    product.updated_at = datetime.now(UTC)
