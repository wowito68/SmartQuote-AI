from uuid import UUID

from app.application.dtos.quotes import (
    QuoteResponse,
    QuoteUploadResponse,
    UploadQuoteCommand,
    UploadQuoteDocumentCommand,
)
from app.application.exceptions import TenderNotFound
from app.application.ports.file_storage import FileStorage
from app.application.ports.quote_analysis_queue import QuoteAnalysisQueue
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.application.use_cases.quotes import GetQuote, UploadQuoteDocument, UploadSupplierQuote
from app.domain.documents.value_objects import DocumentStatus
from app.domain.quotes.analysis import mark_ready_for_analysis
from app.domain.quotes.events import quote_event
from app.domain.quotes.exceptions import InvalidQuoteState
from app.domain.rfqs.value_objects import RfqStatus
from app.domain.suppliers.exceptions import SupplierNotFound
from app.domain.suppliers.value_objects import SupplierStatus
from app.domain.tenders.value_objects import TenderStatus


class SynchronizeTenderForQuoteAnalysis:
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
                raise InvalidQuoteState(
                    "Tender requires an approved catalog before supplier quotes."
                )
            tender_supplier = uow.suppliers.get_tender_supplier(tender_supplier_id)
            if tender_supplier is None or tender_supplier.tender_id != tender_id:
                raise InvalidQuoteState(
                    "Tender supplier was not found for quote analysis."
                )
            if tender_supplier.status not in {
                SupplierStatus.APPROVED,
                SupplierStatus.CONTACTED,
                SupplierStatus.RESPONDED,
            }:
                raise InvalidQuoteState(
                    "Supplier must be approved before a quote can be loaded."
                )
            sent_rfqs = [
                rfq
                for rfq in uow.rfqs.list_rfqs(tender_id)
                if rfq.tender_supplier_id == tender_supplier_id
                and rfq.status
                in {RfqStatus.SENT, RfqStatus.DELIVERED, RfqStatus.RESPONDED}
            ]
            if not sent_rfqs:
                raise InvalidQuoteState(
                    "A sent RFQ is required before a quote can be loaded."
                )
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
                raise InvalidQuoteState(
                    "Tender cannot accept quotes from its current state."
                )
            if tender.status is not previous_status:
                uow.tenders.update(tender)
                uow.audit_events.append(
                    quote_event(
                        tender.id,
                        "TenderWorkflowSynchronized",
                        aggregate_type="tender",
                        previous_status=previous_status.value,
                        current_status=tender.status.value,
                        reason="verified_persisted_artifacts",
                    )
                )
                uow.commit()
            return tender.status


class UploadSupplierQuoteWorkflow:
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


class UploadQuoteDocumentWorkflow:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        file_storage: FileStorage,
        queue: QuoteAnalysisQueue,
        *,
        maximum_size_bytes: int,
    ) -> None:
        self._uow_factory = uow_factory
        self._synchronize = SynchronizeTenderForQuoteAnalysis(uow_factory)
        self._upload = UploadQuoteDocument(
            uow_factory,
            file_storage,
            queue,
            maximum_size_bytes=maximum_size_bytes,
        )

    def execute(self, command: UploadQuoteDocumentCommand) -> QuoteUploadResponse:
        with self._uow_factory() as uow:
            tender_supplier = uow.suppliers.find_tender_supplier(
                command.tender_id,
                command.supplier_id,
            )
            if tender_supplier is None:
                raise SupplierNotFound(
                    "Supplier is not associated with this tender."
                )
            tender_supplier_id = tender_supplier.id
        self._synchronize.execute(command.tender_id, tender_supplier_id)
        result = self._upload.execute(
            UploadQuoteDocumentCommand(
                tender_id=command.tender_id,
                supplier_id=command.supplier_id,
                uploaded_by_user_id=command.uploaded_by_user_id,
                file=command.file,
                rfq_request_id=command.rfq_request_id,
                correlation_id=command.correlation_id,
                auto_process=False,
            )
        )
        if result.duplicate_detected:
            return result
        with self._uow_factory() as uow:
            quote = uow.quotes.get_quote(result.quote.id, for_update=True)
            if quote is None:
                raise InvalidQuoteState("Received quote could not be loaded.")
            mark_ready_for_analysis(quote)
            uow.quotes.update_quote(quote)
            uow.audit_events.append(
                quote_event(
                    quote.id,
                    "quote.ready_for_analysis",
                    uploaded_by_user_id=str(command.uploaded_by_user_id),
                )
            )
            uow.audit_events.append(
                quote_event(
                    quote.id,
                    "QuoteReadyForAnalysis",
                    uploaded_by_user_id=str(command.uploaded_by_user_id),
                )
            )
            uow.commit()
        return QuoteUploadResponse(
            quote=GetQuote(self._uow_factory).execute(result.quote.id),
            duplicate_detected=False,
            queued=False,
        )
