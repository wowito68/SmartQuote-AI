from dataclasses import dataclass
from uuid import UUID

from app.application.ports.unit_of_work import UnitOfWork
from app.domain.catalog.value_objects import ProductStatus
from app.domain.rfqs.entities import RfqRequest
from app.domain.rfqs.exceptions import InvalidRfqState, RfqGenerationError
from app.domain.rfqs.value_objects import EmailAddress, RfqStatus
from app.domain.suppliers.entities import SupplierContact, TenderSupplier
from app.domain.suppliers.value_objects import SupplierContactType, SupplierStatus
from app.domain.tenders.value_objects import TenderStatus

_ALLOWED_RFQ_ROLES = {"admin", "buyer", "procurement"}


@dataclass(frozen=True, slots=True)
class ValidatedRfqContext:
    tender_supplier: TenderSupplier
    contact: SupplierContact


def require_authorized_user(uow: UnitOfWork, user_id: UUID) -> None:
    authorization = uow.users.get_authorization(user_id)
    if authorization is None:
        raise InvalidRfqState("RFQ user does not exist.")
    if not authorization.is_active:
        raise InvalidRfqState("Inactive users cannot perform RFQ delivery actions.")
    if authorization.role.casefold() not in _ALLOWED_RFQ_ROLES:
        raise InvalidRfqState("User is not authorized for RFQ delivery actions.")


def validate_supplier_contact(
    uow: UnitOfWork,
    *,
    tender_id: UUID,
    supplier_id: UUID,
    contact_id: UUID,
) -> ValidatedRfqContext:
    tender_supplier = uow.suppliers.find_tender_supplier(tender_id, supplier_id)
    if tender_supplier is None or tender_supplier.status is not SupplierStatus.APPROVED:
        raise RfqGenerationError("RFQ requires an approved supplier for this tender.")
    supplier = uow.suppliers.get_supplier(supplier_id)
    if supplier is None or supplier.merged_into_supplier_id is not None:
        raise RfqGenerationError("RFQ supplier is unavailable or has been merged.")
    contact = next(
        (item for item in uow.suppliers.list_contacts(supplier_id) if item.id == contact_id),
        None,
    )
    if contact is None or contact.supplier_id != supplier_id:
        raise RfqGenerationError("RFQ contact does not belong to the selected supplier.")
    if contact.contact_type is not SupplierContactType.EMAIL:
        raise RfqGenerationError("RFQ contact must be an email contact.")
    EmailAddress(contact.value)
    if not contact.source_url:
        raise RfqGenerationError("RFQ contact requires a traceable source.")
    return ValidatedRfqContext(tender_supplier=tender_supplier, contact=contact)


def validate_products(uow: UnitOfWork, tender_id: UUID, product_ids: tuple[UUID, ...]):
    if not product_ids:
        raise RfqGenerationError("RFQ requires at least one explicitly selected product.")
    products = []
    seen: set[UUID] = set()
    for product_id in product_ids:
        if product_id in seen:
            continue
        seen.add(product_id)
        product = uow.catalogs.get_product(product_id)
        if (
            product is None
            or product.tender_id != tender_id
            or product.status is not ProductStatus.APPROVED
        ):
            raise RfqGenerationError("Every RFQ product must be approved for this tender.")
        products.append(product)
    return tuple(products)


def validate_rfq_send(uow: UnitOfWork, rfq: RfqRequest, user_id: UUID) -> ValidatedRfqContext:
    require_authorized_user(uow, user_id)
    tender = uow.tenders.get_by_id(rfq.tender_id)
    if tender is None or tender.is_deleted:
        raise InvalidRfqState("RFQ tender is unavailable.")
    if tender.status in {TenderStatus.CLOSED, TenderStatus.CANCELLED}:
        raise InvalidRfqState("Closed or cancelled tenders cannot send RFQs.")
    if rfq.status not in {
        RfqStatus.APPROVED,
        RfqStatus.QUEUED,
        RfqStatus.SENDING,
        RfqStatus.FAILED,
        RfqStatus.RETRY_PENDING,
    }:
        raise InvalidRfqState("RFQ must be approved before delivery.")
    if rfq.contact_id is None:
        raise InvalidRfqState("RFQ has no validated supplier contact.")
    context = validate_supplier_contact(
        uow,
        tender_id=rfq.tender_id,
        supplier_id=rfq.supplier_id,
        contact_id=rfq.contact_id,
    )
    if tuple(rfq.to_recipients) != (EmailAddress(context.contact.value).value,):
        raise InvalidRfqState("RFQ primary recipient no longer matches the approved contact.")
    product_ids = tuple(UUID(str(item["product_id"])) for item in rfq.products)
    validate_products(uow, rfq.tender_id, product_ids)
    snapshot = uow.catalogs.get_snapshot(rfq.catalog_snapshot_id)
    if snapshot is None:
        raise InvalidRfqState("RFQ catalog snapshot is unavailable.")
    return context
