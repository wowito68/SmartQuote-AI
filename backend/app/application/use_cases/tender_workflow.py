from uuid import UUID

from app.application.dtos.quotes import QuoteResponse, UploadQuoteCommand
from app.application.exceptions import TenderNotFound
from app.application.ports.file_storage import FileStorage
from app.application.ports.quote_analysis_queue import QuoteAnalysisQueue
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.application.use_cases.quotes import UploadSupplierQuote
from app.domain.documents.value_objects import DocumentStatus
from app.domain.quotes.events import quote_event
from app.domain.quotes.exceptions import InvalidQuoteState
from app.domain.rfqs.value_objects import RfqStatus
from app.domain.suppliers.value_objects import SupplierStatus
from app.domain.tenders.value_objects import TenderStatus


class SynchronizeTenderForQuoteAnalysis:
    """Repair legacy tender-state drift using already-verified MVP artifacts.

    Iterations 1-8 persisted document, catalog, supplier and RFQ artifacts without
    advancing every global TenderStatus milestone. This compatibility bridge keeps
    the strict domain graph and replays only sequential transitions supported by
    persisted evidence. It stops at waiting_quotes before the quote is accepted.
    """

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, tender_id: UUID, tender_supplier_id: UUID) -> TenderStatus:
        with self._uow_factory() as uow:
            tender = uow.tenders.get_by_id(tender_id)
            if tender is None:
                raise TenderNotFound("Tender was not found.")
            if tender.status in {
                TenderStatus.CANCELLED,
                TenderStatus.CLOSED,
                TenderStatus.AWARDED,
                TenderStatus.COMPARISON_READY,
            }:
                raise InvalidQuoteState("Tender no longer accepts supplier quotes.")
            if tender.status is TenderStatus.QUOTE_ANALYSIS:
                return tender.status

            documents = uow.documents.list_by_tender(tender_id)
            if not documents or any(
                document.status is not DocumentStatus.READY_FOR_AI for document in documents
            ):
                raise InvalidQuoteState(
                    "Tender documents must be fully processed before supplier quotes."
                )
            if uow.catalogs.get_latest_snapshot(tender_id) is None:
                raise InvalidQuoteState("Tender requires an approved catalog before supplier quotes.")

            tender_supplier = uow.suppliers.get_tender_supplier(tender_supplier_id)
            if tender_supplier is None or tender_supplier.tender_id != tender_id:
                raise InvalidQuoteState("Tender supplier was not found for quote analysis.")
            if tender_supplier.status not in {
                SupplierStatus.APPROVED,
                SupplierStatus.CONTACTED,
                SupplierStatus.RESPONDED,
            }:
                raise InvalidQuoteState("Supplier must be approved before a quote can be loaded.")

            sent_rfqs = [
                rfq
                for rfq in uow.rfqs.list_rfqs(tender_id)
                if rfq.tender_supplier_id == tender_supplier_id
                and rfq.status in {RfqStatus.SENT, RfqStatus.DELIVERED, RfqStatus.RESPONDED}
            ]
            if not sent_rfqs:
                raise InvalidQuoteState("A sent RFQ is required before a quote can be loaded.")

            previous_status = tender.status
            if tender.status is TenderStatus.DRAFT:
                tender.change_status(TenderStatus.DOCUMENTS_PENDING)
            if tender.status is TenderStatus.DOCUMENTS_PENDING:
                tender.change_status(TenderStatus.DOCUMENTS_PROCESSING)
            if tender.status is TenderStatus.DOCUMENTS_PROCESSING:
                tender.change_status(TenderStatus.CATALOG_REVIEW)
            if tender.status is TenderStatus.CATALOG_REVIEW:
                tender.change_status(TenderStatus.SUPPLIER_REVIEW)
            if tender.status is TenderStatus.SUPPLIER_REVIEW:
                tender.change_status(TenderStatus.RFQ_READY)
            if tender.status is TenderStatus.RFQ_READY:
                tender.change_status(TenderStatus.WAITING_QUOTES)
            if tender.status is not TenderStatus.WAITING_QUOTES:
                raise InvalidQuoteState("Tender cannot accept quotes from its current state.")

            if tender.status is not previous_status:
                uow.tenders.update(tender)
                uow.audit_events.append(
                    quote_event(
                        tender.id,
                        "TenderWorkflowSynchronized",
                        aggregate_type="tender",
                        previous_status=previous_status.value,
                        current_status=tender.status.value,
                        reason="verified_iteration_9_artifacts",
                    )
                )
                uow.commit()
            return tender.status


class UploadSupplierQuoteWorkflow:
    """Application orchestration for quote upload plus global tender progression."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        file_storage: FileStorage,
        queue: QuoteAnalysisQueue,
        *,
        maximum_size_bytes: int,
    ) -> None:
        self._upload = UploadSupplierQuote(
            uow_factory,
            file_storage,
            queue,
            maximum_size_bytes=maximum_size_bytes,
        )
        self._synchronize = SynchronizeTenderForQuoteAnalysis(uow_factory)

    def execute(self, command: UploadQuoteCommand) -> QuoteResponse:
        self._synchronize.execute(command.tender_id, command.tender_supplier_id)
        return self._upload.execute(command)
