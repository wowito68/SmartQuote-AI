from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.comparison.entities import (
    Comparison,
    ComparisonItem,
    ComparisonOffer,
    ComparisonWarning,
)
from app.domain.comparison.value_objects import (
    ComparisonStatus,
    ComparisonWarningCode,
    DeliveryTime as ComparisonDeliveryTime,
    MonetaryComparisonStatus,
    Money as ComparisonMoney,
    NormalizedCompliance,
    OfferStatus,
    Quantity as ComparisonQuantity,
    QuantityComparisonStatus,
    WarningSeverity,
)
from app.domain.documents.processing import DocumentPage, DocumentQuality, ExtractionRun
from app.domain.documents.value_objects import (
    DocumentQualityDecision,
    DocumentQualityLevel,
    ExtractionRunStatus,
)
from app.domain.quotes.entities import (
    Quote,
    QuoteDocument,
    QuoteEvidenceReference,
    QuoteExtractionRun,
    QuoteItem,
    QuoteTaskRecord,
)
from app.domain.quotes.exceptions import InvalidQuoteState
from app.domain.quotes.value_objects import (
    ComplianceStatus,
    EvidenceFindingStatus,
    ProductMatchStatus,
    QuoteDocumentProcessingStatus,
    QuoteDocumentType,
    QuoteExtractionRunStatus,
    QuoteStatus,
    QuoteTaskStatus,
    QuoteWarning,
)
from app.domain.rfqs.entities import (
    EmailAttachment,
    EmailMessage,
    EmailTemplate,
    OutboundMessageLog,
    RfqRequest,
    RfqTaskRecord,
    RfqVersionSnapshot,
    build_send_idempotency_key,
)
from app.domain.rfqs.exceptions import AttachmentValidationError, InvalidRfqState
from app.domain.rfqs.value_objects import (
    EmailMessageStatus,
    OutboundLogResult,
    RfqStatus,
    TaskRecordStatus,
)
from app.domain.shared.exceptions import ValidationError
from app.domain.suppliers.entities import (
    ProductSupplierMatch,
    Supplier,
    SupplierContact,
    SupplierDiscoveryRun,
    SupplierMergeSuggestion,
    SupplierSource,
    TenderSupplier,
)
from app.domain.suppliers.exceptions import (
    InvalidSupplierDiscoveryState,
    InvalidSupplierState,
    SupplierMergeConflict,
)
from app.domain.suppliers.value_objects import (
    MergeSuggestionStatus,
    SupplierConfidence,
    SupplierContactType,
    SupplierDiscoveryRunStatus,
    SupplierDiscoveryStage,
    SupplierMatchScore,
    SupplierStatus,
)


def make_quote(**overrides) -> Quote:
    values = {
        "tender_id": uuid4(),
        "tender_supplier_id": uuid4(),
        "supplier_id": uuid4(),
        "original_file_name": " supplier quote.pdf ",
        "storage_key": "private/quote.pdf",
        "mime_type": "application/pdf",
        "file_size": 100,
        "file_hash": "a" * 64,
        "uploaded_by_user_id": uuid4(),
    }
    values.update(overrides)
    return Quote(**values)


def make_extraction_run(**overrides) -> QuoteExtractionRun:
    values = {
        "quote_id": uuid4(),
        "tender_id": uuid4(),
        "supplier_id": uuid4(),
        "idempotency_key": "b" * 64,
        "extractor_version": "1.0",
        "prompt_version": "2.0",
        "model": "test-model",
        "schema_version": "2.0",
        "schema_hash": "c" * 64,
        "extractor_name": "office-parser",
    }
    values.update(overrides)
    return QuoteExtractionRun(**values)


def make_rfq(**overrides) -> RfqRequest:
    values = {
        "tender_id": uuid4(),
        "tender_supplier_id": uuid4(),
        "supplier_id": uuid4(),
        "catalog_snapshot_id": uuid4(),
        "generated_by_user_id": uuid4(),
        "response_deadline": datetime.now(UTC) + timedelta(days=7),
        "template_name": "rfq",
        "template_version": "1.0",
        "subject": "Request for quotation",
        "body": "Please provide your quotation.",
        "products": ({"name": "Sensor", "quantity": "2"},),
        "generation_key": "d" * 64,
        "to_recipients": ("BUYER@EXAMPLE.COM", "buyer@example.com"),
    }
    values.update(overrides)
    return RfqRequest(**values)


def make_discovery_run(**overrides) -> SupplierDiscoveryRun:
    values = {
        "tender_id": uuid4(),
        "catalog_snapshot_id": uuid4(),
        "requested_by_user_id": uuid4(),
        "idempotency_key": "e" * 64,
        "search_provider": "mock-search",
        "search_provider_version": "1",
        "search_configuration": {"limit": 10},
        "matching_algorithm_version": "1.0",
    }
    values.update(overrides)
    return SupplierDiscoveryRun(**values)


def test_quote_metadata_and_summary_invariants() -> None:
    with pytest.raises(ValidationError):
        make_quote(original_file_name=" ")
    with pytest.raises(ValidationError):
        make_quote(file_size=0)
    with pytest.raises(ValidationError):
        make_quote(file_hash="bad")
    with pytest.raises(ValidationError):
        make_quote(version=0)
    with pytest.raises(ValidationError):
        make_quote(currency="peso")
    with pytest.raises(ValidationError):
        make_quote(delivery_time_days=-1)
    with pytest.raises(ValidationError):
        make_quote(total_amount=Decimal("NaN"))

    quote = make_quote(currency="mxn", valid_until=datetime(2030, 1, 1))
    assert quote.original_file_name == "supplier quote.pdf"
    assert quote.currency == "MXN"
    assert quote.valid_until is not None and quote.valid_until.tzinfo is UTC
    with pytest.raises(InvalidQuoteState):
        quote.apply_summary(
            currency="MXN",
            subtotal_amount=Decimal("1"),
            tax_amount=Decimal("0"),
            total_amount=Decimal("1"),
            delivery_time_days=1,
            commercial_terms=None,
            valid_until=None,
        )
    with pytest.raises(InvalidQuoteState):
        quote.start_extraction()


def test_quote_review_rejection_reprocess_and_failure_lifecycle() -> None:
    quote = make_quote()
    quote.start_validation()
    quote.start_validation()
    quote.start_extraction()
    quote.mark_extracted()
    with pytest.raises(ValidationError):
        quote.apply_summary(
            currency="MXN",
            subtotal_amount=Decimal("100"),
            tax_amount=Decimal("16"),
            total_amount=Decimal("116"),
            delivery_time_days=-1,
            commercial_terms="net 30",
            valid_until=None,
        )
    quote.apply_summary(
        currency="mxn",
        subtotal_amount=Decimal("100"),
        tax_amount=Decimal("16"),
        total_amount=Decimal("116"),
        delivery_time_days=5,
        commercial_terms="  net   30  ",
        valid_until=datetime(2030, 1, 1),
    )
    quote.start_review()
    quote.record_manual_edit()
    assert quote.manual_edit_count == 1 and quote.version == 2
    with pytest.raises(ValidationError):
        quote.reject(uuid4(), "   ")
    reviewer = uuid4()
    quote.reject(reviewer, " incorrect pricing ")
    assert quote.status is QuoteStatus.REJECTED
    quote.restart_processing()
    assert quote.status is QuoteStatus.VALIDATING and quote.last_error is None
    quote.mark_failed(RuntimeError("provider down"))
    quote.mark_failed("still down")
    assert quote.last_error == "still down"
    quote.record_error(ValueError("bad data"))
    assert quote.last_error == "ValueError: bad data"


def test_quote_approval_is_immutable_and_failure_is_guarded() -> None:
    quote = make_quote()
    quote.start_validation()
    quote.start_extraction()
    quote.mark_extracted()
    quote.mark_normalized()
    quote.start_review()
    run_id = uuid4()
    reviewer = uuid4()
    quote.approve(reviewer, run_id)
    assert quote.approved_extraction_run_id == run_id
    with pytest.raises(InvalidQuoteState):
        quote.record_manual_edit()
    with pytest.raises(InvalidQuoteState):
        quote.mark_failed("late failure")
    quote.include_in_comparison()
    with pytest.raises(InvalidQuoteState):
        quote.restart_processing()


def test_quote_document_processing_and_validation() -> None:
    base = {
        "quote_id": uuid4(),
        "storage_key": "private/q.xlsx",
        "original_file_name": "q.xlsx",
        "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "file_size": 200,
        "file_hash": "f" * 64,
        "document_type": QuoteDocumentType.XLSX,
    }
    with pytest.raises(ValidationError):
        QuoteDocument(**{**base, "storage_key": " "})
    with pytest.raises(ValidationError):
        QuoteDocument(**{**base, "file_size": 0})
    with pytest.raises(ValidationError):
        QuoteDocument(**{**base, "file_hash": "bad"})

    document = QuoteDocument(**base)
    document.start_processing("ooxml", "1.0")
    assert document.processing_status is QuoteDocumentProcessingStatus.PROCESSING
    document.start_processing("ignored", "2.0")
    assert document.extractor_name == "ooxml"
    document.complete()
    assert document.processing_status is QuoteDocumentProcessingStatus.PROCESSED
    document.fail(ValueError("broken workbook"))
    assert document.processing_status is QuoteDocumentProcessingStatus.FAILED
    document.start_processing("ooxml", "1.1")
    assert document.last_error is None


def test_quote_extraction_run_tracks_usage_failure_restart_and_approval() -> None:
    with pytest.raises(ValidationError):
        make_extraction_run(idempotency_key="bad")
    with pytest.raises(ValidationError):
        make_extraction_run(extraction_fingerprint="bad")
    with pytest.raises(ValidationError):
        make_extraction_run(model=" ")
    with pytest.raises(ValidationError):
        make_extraction_run(run_number=0)

    run = make_extraction_run(extraction_fingerprint="d" * 64)
    run.start()
    assert run.status is QuoteExtractionRunStatus.RUNNING
    run.complete(
        provider_response_id="resp_1",
        input_tokens=-2,
        output_tokens=-3,
        estimated_cost_usd=Decimal("-1"),
        raw_response={"ok": True},
        duration_ms=-10,
    )
    assert run.input_tokens == 0 and run.estimated_cost_usd == 0
    run.start()
    assert run.status is QuoteExtractionRunStatus.COMPLETED
    run.fail(RuntimeError("provider failure"))
    assert run.error_type == "RuntimeError"
    run.restart()
    assert run.status is QuoteExtractionRunStatus.QUEUED and run.completed_at is None
    run.mark_approved_source()
    assert run.is_approved_source is True


def test_quote_evidence_requires_valid_locator_fragment_and_confidence() -> None:
    values = {
        "quote_id": uuid4(),
        "quote_document_id": uuid4(),
        "extraction_run_id": uuid4(),
        "entity_type": "quote_item",
        "entity_id": uuid4(),
        "field_name": "unit_price",
        "locator_type": "page",
        "locator": "page:1",
        "fragment": "$100.00",
        "extraction_method": "ai",
        "finding_status": EvidenceFindingStatus.FOUND,
        "confidence": 0.9,
    }
    evidence = QuoteEvidenceReference(**values)
    assert evidence.fragment == "$100.00"
    with pytest.raises(ValidationError):
        QuoteEvidenceReference(**{**values, "entity_type": "supplier"})
    with pytest.raises(ValidationError):
        QuoteEvidenceReference(**{**values, "field_name": " "})
    with pytest.raises(ValidationError):
        QuoteEvidenceReference(**{**values, "locator": " "})
    with pytest.raises(ValidationError):
        QuoteEvidenceReference(**{**values, "fragment": " "})
    with pytest.raises(ValidationError):
        QuoteEvidenceReference(**{**values, "confidence": 1.1})


def test_quote_item_validation_warnings_human_review_and_snapshot() -> None:
    with pytest.raises(ValidationError):
        QuoteItem(uuid4(), " ", None, None, None, None, None, None)
    with pytest.raises(ValidationError):
        QuoteItem(uuid4(), "Sensor", Decimal("0"), None, None, None, None, None)
    with pytest.raises(ValidationError):
        QuoteItem(uuid4(), "Sensor", Decimal("1"), None, None, "PESO", None, None)
    with pytest.raises(ValidationError):
        QuoteItem(uuid4(), "Sensor", Decimal("1"), None, None, None, -1, None)
    with pytest.raises(ValidationError):
        QuoteItem(
            uuid4(),
            "Sensor",
            Decimal("1"),
            None,
            None,
            None,
            None,
            None,
            source_page=0,
        )
    with pytest.raises(ValidationError):
        QuoteItem(
            uuid4(),
            "Sensor",
            Decimal("1"),
            None,
            None,
            None,
            None,
            None,
            confidence=1.1,
        )

    item = QuoteItem(
        quote_id=uuid4(),
        product_name=" Sensor A ",
        quantity=None,
        unit_price=Decimal("10"),
        total_price=Decimal("50"),
        currency=None,
        delivery_days=None,
        technical_compliance=False,
        match_status=ProductMatchStatus.POSSIBLE_MATCH,
        match_score=Decimal("0.7"),
        confidence=0.4,
        quoted_specifications={" voltage ": " 24 V ", "blank": " "},
        warnings=("OLD", "OLD"),
    )
    assert item.compliance_status is ComplianceStatus.NON_COMPLIANT
    assert item.quoted_specifications == {"voltage": "24 V"}
    item.recalculate_warnings()
    assert QuoteWarning.CURRENCY_UNKNOWN.value in item.warnings
    assert QuoteWarning.QUANTITY_UNKNOWN.value in item.warnings
    assert QuoteWarning.POSSIBLE_PRODUCT_MATCH.value in item.warnings
    assert QuoteWarning.TECHNICAL_NON_COMPLIANCE.value in item.warnings
    assert QuoteWarning.LOW_CONFIDENCE.value in item.warnings

    product_id = uuid4()
    item.apply_human_review(
        catalog_product_id=product_id,
        product_name="Reviewed Sensor",
        description="industrial",
        brand="Acme",
        model="S1",
        quantity=Decimal("2"),
        unit="piece",
        unit_price=Decimal("100"),
        total_price=Decimal("200"),
        currency="mxn",
        delivery_days=3,
        compliance_status=ComplianceStatus.COMPLIANT,
        notes="accepted",
    )
    snapshot = item.snapshot()
    assert snapshot["catalog_product_id"] == str(product_id)
    assert snapshot["currency"] == "MXN"
    assert item.technical_compliance is True
    with pytest.raises(ValidationError):
        item.apply_human_review(
            catalog_product_id=None,
            product_name=None,
            description=None,
            brand=None,
            model=None,
            quantity=Decimal("0"),
            unit=None,
            unit_price=None,
            total_price=None,
            currency=None,
            delivery_days=None,
            compliance_status=None,
            notes=None,
        )
    with pytest.raises(ValidationError):
        item.apply_human_review(
            catalog_product_id=None,
            product_name=None,
            description=None,
            brand=None,
            model=None,
            quantity=None,
            unit=None,
            unit_price=None,
            total_price=None,
            currency="peso",
            delivery_days=None,
            compliance_status=None,
            notes=None,
        )
    with pytest.raises(ValidationError):
        item.apply_human_review(
            catalog_product_id=None,
            product_name=None,
            description=None,
            brand=None,
            model=None,
            quantity=None,
            unit=None,
            unit_price=None,
            total_price=None,
            currency=None,
            delivery_days=-1,
            compliance_status=None,
            notes=None,
        )


def test_quote_task_record_tracks_retry_and_terminal_results() -> None:
    task = QuoteTaskRecord(quote_id=uuid4(), correlation_id="corr-1")
    task.start()
    assert task.status is QuoteTaskStatus.RUNNING and task.attempt_count == 1
    task.fail(RuntimeError("temporary"), retryable=True)
    assert task.status is QuoteTaskStatus.RETRY_PENDING and task.completed_at is None
    task.start()
    task.fail(RuntimeError("permanent"), retryable=False)
    assert task.status is QuoteTaskStatus.FAILED and task.completed_at is not None
    task.succeed()
    assert task.status is QuoteTaskStatus.SUCCEEDED and task.last_error is None


def test_document_processing_entities_cover_success_failure_and_reuse() -> None:
    with pytest.raises(ValidationError):
        DocumentPage(uuid4(), uuid4(), 0, "text", 10, 10, 0)
    with pytest.raises(ValidationError):
        DocumentPage(uuid4(), uuid4(), 1, "text", 0, 10, 0)
    with pytest.raises(ValidationError):
        DocumentPage(uuid4(), uuid4(), 1, "text", 10, 10, -1)
    page = DocumentPage(uuid4(), uuid4(), 1, "hello world", 612, 792, 5)
    assert page.character_count == 11
    assert page.word_count == 2
    assert page.is_empty is False
    assert page.text_density > 0

    with pytest.raises(ValidationError):
        ExtractionRun(uuid4(), "bad", "pdf", "1", {})
    with pytest.raises(ValidationError):
        ExtractionRun(uuid4(), "a" * 64, " ", "1", {})
    run = ExtractionRun(uuid4(), "a" * 64, "pdf", "1", {})
    run.complete([page], -5)
    assert run.status is ExtractionRunStatus.COMPLETED and run.duration_ms == 0
    run.restart()
    assert run.status is ExtractionRunStatus.RUNNING and run.pages_processed == 0
    run.fail(RuntimeError("extractor failed"))
    assert run.status is ExtractionRunStatus.FAILED and run.error_type == "RuntimeError"
    source_id = uuid4()
    run.mark_reused(source_id)
    assert run.status is ExtractionRunStatus.REUSED and run.reused_from_run_id == source_id

    quality_values = {
        "document_id": uuid4(),
        "extraction_run_id": uuid4(),
        "pages_processed": 2,
        "empty_pages": 1,
        "characters_extracted": 100,
        "empty_page_percentage": 50.0,
        "text_density": 3.0,
        "quality_level": DocumentQualityLevel.MEDIUM,
        "decision": DocumentQualityDecision.READY_FOR_AI,
        "requires_manual_review": False,
    }
    assert DocumentQuality(**quality_values).pages_processed == 2
    with pytest.raises(ValidationError):
        DocumentQuality(**{**quality_values, "pages_processed": -1})
    with pytest.raises(ValidationError):
        DocumentQuality(**{**quality_values, "empty_pages": 3})
    with pytest.raises(ValidationError):
        DocumentQuality(**{**quality_values, "empty_page_percentage": 101})
    with pytest.raises(ValidationError):
        DocumentQuality(**{**quality_values, "text_density": -1})


def test_rfq_template_attachment_and_idempotency_guards() -> None:
    assert EmailTemplate("rfq", "1", "Subject", "Body", "text/html").content_type == "text/html"
    with pytest.raises(ValidationError):
        EmailTemplate("", "1", "Subject", "Body")
    with pytest.raises(ValidationError):
        EmailTemplate("rfq", "1", " ", "Body")
    with pytest.raises(ValidationError):
        EmailTemplate("rfq", "1", "Subject", "Body", "application/json")

    values = {
        "rfq_id": uuid4(),
        "document_id": uuid4(),
        "original_file_name": "spec.pdf",
        "file_hash": "a" * 64,
        "file_size": 10,
        "mime_type": "application/pdf",
    }
    attachment = EmailAttachment(**values)
    assert attachment.snapshot()["name"] == "spec.pdf"
    with pytest.raises(AttachmentValidationError):
        EmailAttachment(**{**values, "original_file_name": "../spec.pdf"})
    with pytest.raises(AttachmentValidationError):
        EmailAttachment(**{**values, "file_hash": "bad"})
    with pytest.raises(AttachmentValidationError):
        EmailAttachment(**{**values, "file_size": 0})
    with pytest.raises(AttachmentValidationError):
        EmailAttachment(**{**values, "mime_type": "text/plain"})

    rfq_id = uuid4()
    first = build_send_idempotency_key(rfq_id, 1, ("b@example.com", "a@example.com"))
    second = build_send_idempotency_key(rfq_id, 1, ("a@example.com", "b@example.com"))
    assert first == second and len(first) == 64


def test_rfq_validation_edit_approval_and_delivery_lifecycle() -> None:
    with pytest.raises(ValidationError):
        make_rfq(response_deadline=datetime.now(UTC) - timedelta(days=1))
    with pytest.raises(ValidationError):
        make_rfq(template_name=" ")
    with pytest.raises(ValidationError):
        make_rfq(subject=" ")
    with pytest.raises(ValidationError):
        make_rfq(body=" ")
    with pytest.raises(ValidationError):
        make_rfq(products=())
    with pytest.raises(ValidationError):
        make_rfq(generation_key="bad")
    with pytest.raises(ValidationError):
        make_rfq(generation_duration_ms=-1)

    rfq = make_rfq()
    assert rfq.to_recipients == ("buyer@example.com",)
    rfq.start_review()
    rfq.edit(
        subject="Updated RFQ",
        body="Updated body",
        to_recipients=("sales@example.com",),
        cc_recipients=("copy@example.com",),
        bcc_recipients=("audit@example.com",),
        response_deadline=datetime.now(UTC) + timedelta(days=10),
        observations=" priority ",
        contact_name=" Sales Team ",
    )
    assert rfq.status is RfqStatus.DRAFT and rfq.version == 2
    rfq.start_review()
    rfq.reject_review()
    assert rfq.status is RfqStatus.DRAFT
    rfq.record_attachment_edit()
    assert rfq.version == 3
    rfq.start_review()
    rfq.approve(uuid4(), ())
    assert rfq.status is RfqStatus.APPROVED and rfq.send_idempotency_key
    with pytest.raises(InvalidRfqState):
        rfq.edit(subject="too late")
    rfq.queue(uuid4())
    rfq.start_sending()
    rfq.mark_sent()
    rfq.mark_delivered()
    assert rfq.status is RfqStatus.DELIVERED
    with pytest.raises(InvalidRfqState):
        rfq.cancel(uuid4(), "too late")


def test_rfq_failure_retry_cancel_and_approval_guards() -> None:
    rfq = make_rfq(to_recipients=())
    rfq.start_review()
    with pytest.raises(ValidationError):
        rfq.approve(uuid4(), ())
    with pytest.raises(InvalidRfqState):
        rfq.queue(uuid4())

    retry = make_rfq()
    retry.start_review()
    retry.approve(uuid4(), ())
    retry.queue(uuid4())
    retry.mark_failed(" smtp unavailable ")
    retry.mark_retry_pending(" retry later ")
    assert retry.status is RfqStatus.RETRY_PENDING
    retry.queue(uuid4())
    retry.cancel(uuid4(), " operator cancelled ")
    assert retry.status is RfqStatus.CANCELLED
    with pytest.raises(InvalidRfqState):
        retry.start_review()


def test_rfq_snapshots_email_messages_tasks_and_logs() -> None:
    snapshot = RfqVersionSnapshot(
        rfq_id=uuid4(),
        version=1,
        changed_by_user_id=uuid4(),
        status=RfqStatus.DRAFT,
        contact_id=None,
        subject="Subject",
        body="Body",
        to_recipients=("A@example.com",),
        cc_recipients=(),
        bcc_recipients=(),
        products=({"name": "Sensor"},),
        attachment_snapshot=(),
        change_reason=" edit ",
    )
    assert snapshot.to_recipients == ("a@example.com",)
    with pytest.raises(ValidationError):
        RfqVersionSnapshot(
            rfq_id=uuid4(), version=0, changed_by_user_id=uuid4(), status=RfqStatus.DRAFT,
            contact_id=None, subject="Subject", body="Body", to_recipients=(), cc_recipients=(),
            bcc_recipients=(), products=(), attachment_snapshot=()
        )

    values = {
        "rfq_id": uuid4(),
        "rfq_version": 1,
        "attempt_number": 1,
        "idempotency_key": "f" * 64,
        "provider_name": "simulation",
        "from_address": "Sender@Example.com",
        "to_recipients": ("Buyer@Example.com",),
        "cc_recipients": (),
        "bcc_recipients": (),
        "subject": "Subject",
        "body": "Body",
        "attachment_snapshot": (),
    }
    message = EmailMessage(**values)
    message.start()
    message.succeed(" msg-1 ", -3)
    assert message.status is EmailMessageStatus.SENT and message.duration_ms == 0
    with pytest.raises(InvalidRfqState):
        message.start()
    failed = EmailMessage(**{**values, "id": uuid4(), "attempt_number": 2})
    with pytest.raises(InvalidRfqState):
        failed.fail(RuntimeError("not started"), 1)
    failed.start()
    failed.fail(RuntimeError("smtp failed"), -1)
    assert failed.status is EmailMessageStatus.FAILED and failed.duration_ms == 0

    task = RfqTaskRecord(rfq_id=uuid4(), correlation_id=" corr ")
    task.start()
    task.retry(" temporary ")
    assert task.status is TaskRecordStatus.RETRY_PENDING
    task.start()
    task.fail(" permanent ")
    assert task.status is TaskRecordStatus.FAILED
    task.succeed()
    assert task.status is TaskRecordStatus.SUCCEEDED
    with pytest.raises(ValidationError):
        RfqTaskRecord(rfq_id=uuid4(), correlation_id=" ")

    log = OutboundMessageLog(
        rfq_id=uuid4(), email_message_id=uuid4(), event_type="sent",
        result=OutboundLogResult.SUCCESS, provider_name="simulation", details={}
    )
    assert log.event_type == "sent"
    with pytest.raises(ValidationError):
        OutboundMessageLog(
            rfq_id=uuid4(), email_message_id=uuid4(), event_type=" ",
            result=OutboundLogResult.FAILURE, provider_name="simulation", details={}
        )


def test_supplier_core_contact_source_and_merge_invariants() -> None:
    with pytest.raises(ValidationError):
        Supplier()
    supplier = Supplier(
        legal_name=" Acme SA ", website="https://www.Example.COM/path",
        category=" Sensors ", country=" MX ", city=" Queretaro "
    )
    assert supplier.display_name == "Acme SA" and supplier.normalized_domain == "example.com"
    supplier.edit(
        trade_name=" Acme Sensors ", website="shop.example.com", category="Industrial",
        country="Mexico", city="Qro", description=" supplier "
    )
    assert supplier.display_name == "Acme Sensors"
    with pytest.raises(SupplierMergeConflict):
        supplier.merge_into(supplier.id)
    target = uuid4()
    supplier.merge_into(target)
    with pytest.raises(InvalidSupplierState):
        supplier.edit(city="Mexico City")
    with pytest.raises(SupplierMergeConflict):
        supplier.merge_into(uuid4())

    confidence = SupplierConfidence(0.8)
    email = SupplierContact(
        supplier_id=uuid4(), contact_type=SupplierContactType.EMAIL,
        value=" SALES@EXAMPLE.COM ", confidence=confidence, source_url="https://example.com/contact"
    )
    phone = SupplierContact(
        supplier_id=uuid4(), contact_type=SupplierContactType.PHONE,
        value="+52 442 123 4567", confidence=confidence, source_url="manual://user"
    )
    form = SupplierContact(
        supplier_id=uuid4(), contact_type=SupplierContactType.CONTACT_FORM,
        value="https://example.com/contact/", confidence=confidence, source_url="https://example.com"
    )
    assert email.identity_key == "email:sales@example.com"
    assert phone.identity_key.endswith("524421234567")
    assert form.identity_key == "contact_form:https://example.com/contact"
    with pytest.raises(ValidationError):
        SupplierContact(uuid4(), SupplierContactType.EMAIL, "bad", confidence, "https://source")
    with pytest.raises(ValidationError):
        SupplierContact(uuid4(), SupplierContactType.PHONE, "123", confidence, "https://source")
    with pytest.raises(ValidationError):
        SupplierContact(uuid4(), SupplierContactType.CONTACT_FORM, "not-url", confidence, "https://source")

    source = SupplierSource(
        supplier_id=uuid4(), provider_name="manual", source_type="manual",
        source_url="manual://user/1", metadata={"a": 1}
    )
    assert source.metadata == {"a": 1}
    with pytest.raises(ValidationError):
        SupplierSource(uuid4(), "search", "result", "ftp://example.com")


def test_tender_supplier_review_and_merge_state_machine() -> None:
    relation = TenderSupplier(tender_id=uuid4(), supplier_id=uuid4())
    relation.mark_contact_discovery_complete()
    relation.start_review()
    reviewer = uuid4()
    relation.approve(reviewer)
    assert relation.status is SupplierStatus.APPROVED
    with pytest.raises(InvalidSupplierState):
        relation.reject(reviewer, "late")

    rejected = TenderSupplier(tender_id=uuid4(), supplier_id=uuid4())
    rejected.mark_contact_discovery_complete()
    rejected.start_review()
    with pytest.raises(ValidationError):
        rejected.reject(reviewer, " ")
    rejected.reject(reviewer, " not qualified ")
    assert rejected.status is SupplierStatus.REJECTED

    merged = TenderSupplier(tender_id=uuid4(), supplier_id=uuid4())
    merged.mark_contact_discovery_complete()
    merged.start_review()
    with pytest.raises(SupplierMergeConflict):
        merged.merge_into(merged.id, reviewer)
    merged.merge_into(uuid4(), reviewer)
    assert merged.status is SupplierStatus.MERGED


def test_supplier_discovery_run_stages_fail_restart_and_reuse() -> None:
    with pytest.raises(ValidationError):
        make_discovery_run(idempotency_key="bad")
    with pytest.raises(ValidationError):
        make_discovery_run(search_provider=" ")
    with pytest.raises(ValidationError):
        make_discovery_run(matching_algorithm_version=" ")

    run = make_discovery_run()
    with pytest.raises(InvalidSupplierDiscoveryState):
        run.save_search_results([], duration_ms=1, provider_errors=[])
    run.start()
    run.save_search_results([{"name": "Acme"}], duration_ms=-1, provider_errors=["x"] * 101)
    assert run.current_stage is SupplierDiscoveryStage.DEDUPLICATION
    assert run.search_duration_ms == 0 and len(run.provider_errors) == 100
    run.save_deduplicated([{"name": "Acme"}], duplicates_detected=-1)
    assert run.duplicates_detected == 0
    run.mark_contacts_complete(-5)
    assert run.contacts_found == 0
    run.mark_matching_complete(-2)
    assert run.current_stage is SupplierDiscoveryStage.REVIEW and run.matching_duration_ms == 0
    run.complete()
    assert run.status is SupplierDiscoveryRunStatus.COMPLETED
    run.start()
    assert run.status is SupplierDiscoveryRunStatus.COMPLETED
    run.fail(RuntimeError("search failed"))
    assert run.error_type == "RuntimeError"
    run.restart()
    assert run.status is SupplierDiscoveryRunStatus.QUEUED
    source = uuid4()
    run.mark_reused(source)
    assert run.reused_from_run_id == source and run.status is SupplierDiscoveryRunStatus.REUSED


def test_supplier_matches_and_merge_suggestions_require_traceable_reasons() -> None:
    match = ProductSupplierMatch(
        tender_supplier_id=uuid4(), product_id=uuid4(), score=SupplierMatchScore(80),
        components={"name": 1.0}, reasons=("name match",), algorithm_version="1.0"
    )
    assert match.reason == "name match"
    with pytest.raises(ValidationError):
        ProductSupplierMatch(
            uuid4(), uuid4(), SupplierMatchScore(50), {}, (), "1.0"
        )
    with pytest.raises(ValidationError):
        ProductSupplierMatch(
            uuid4(), uuid4(), SupplierMatchScore(50), {}, ("reason",), " "
        )

    source = uuid4()
    target = uuid4()
    suggestion = SupplierMergeSuggestion(
        source, target, SupplierConfidence(0.9), ("same domain",)
    )
    suggestion.accept(uuid4())
    assert suggestion.status is MergeSuggestionStatus.ACCEPTED
    with pytest.raises(SupplierMergeConflict):
        suggestion.reject(uuid4())
    rejected = SupplierMergeSuggestion(
        uuid4(), uuid4(), SupplierConfidence(0.8), ("similar name",)
    )
    rejected.reject(uuid4())
    assert rejected.status is MergeSuggestionStatus.REJECTED
    with pytest.raises(SupplierMergeConflict):
        SupplierMergeSuggestion(source, source, SupplierConfidence(0.9), ("same",))
    with pytest.raises(ValidationError):
        SupplierMergeSuggestion(uuid4(), uuid4(), SupplierConfidence(0.9), ())


def test_comparison_entities_validate_serialize_complete_and_archive() -> None:
    warning = ComparisonWarning(
        ComparisonWarningCode.MISSING_PRICE,
        WarningSeverity.WARNING,
        " missing price ",
        supplier_id=uuid4(),
    )
    assert warning.as_dict()["code"] == "missing_price"
    with pytest.raises(ValidationError):
        ComparisonWarning(ComparisonWarningCode.MISSING_PRICE, WarningSeverity.WARNING, " ")

    supplier_id = uuid4()
    offer = ComparisonOffer(
        supplier_id=supplier_id,
        supplier_name=" Acme ",
        status=OfferStatus.QUOTED,
        quote_id=uuid4(),
        quote_item_id=uuid4(),
        quoted_product_name="Sensor",
        brand="Acme",
        model="S1",
        quantity=ComparisonQuantity(Decimal("2"), " Piece "),
        quantity_status=QuantityComparisonStatus.MATCHED,
        unit_price=ComparisonMoney(Decimal("100"), "mxn"),
        total_price=ComparisonMoney(Decimal("200"), "MXN"),
        compliance=NormalizedCompliance.COMPLIANT,
        delivery=ComparisonDeliveryTime(3),
        confidence=0.9,
        warnings=(warning,),
    )
    assert offer.as_dict()["currency"] == "MXN"
    with pytest.raises(ValidationError):
        ComparisonOffer(uuid4(), " ", OfferStatus.MISSING)
    with pytest.raises(ValidationError):
        ComparisonOffer(uuid4(), "Acme", OfferStatus.QUOTED, confidence=1.1)
    with pytest.raises(ValidationError):
        ComparisonOffer(
            uuid4(), "Acme", OfferStatus.MISSING, quote_item_id=uuid4(),
            quoted_product_name="Sensor"
        )

    comparison_id = uuid4()
    item = ComparisonItem(
        comparison_id=comparison_id,
        product_id=uuid4(),
        requested_product_name=" Sensor ",
        requested_quantity=ComparisonQuantity(Decimal("2"), "piece"),
        offers=(offer,),
        monetary_status=MonetaryComparisonStatus.COMPARABLE,
    )
    assert item.as_dict()["requested_product"] == "Sensor"
    with pytest.raises(ValidationError):
        ComparisonItem(
            comparison_id, uuid4(), " ", ComparisonQuantity(None, None), (),
            MonetaryComparisonStatus.INSUFFICIENT_DATA
        )
    with pytest.raises(ValidationError):
        ComparisonItem(
            comparison_id, uuid4(), "Sensor", ComparisonQuantity(None, None),
            (offer, offer), MonetaryComparisonStatus.COMPARABLE
        )

    comparison = Comparison(
        tender_id=uuid4(), catalog_snapshot_id=uuid4(), catalog_version=1,
        quotes_version="a" * 64, comparison_version="1.0", comparison_key="b" * 64,
        created_by_user_id=uuid4(), source_quote_ids=(uuid4(),)
    )
    with pytest.raises(ValidationError):
        comparison.complete((item,), ())
    comparison.start()
    comparison.complete((item,), ())
    assert comparison.status is ComparisonStatus.READY
    payload = comparison.as_dict()
    assert payload["items"][0]["offers"][0]["supplier_name"] == "Acme"
    comparison.archive()
    assert comparison.status is ComparisonStatus.ARCHIVED
    with pytest.raises(ValidationError):
        comparison.start()


def test_comparison_critical_warning_marks_result_invalid() -> None:
    critical = ComparisonWarning(
        ComparisonWarningCode.DUPLICATE_QUOTE_ITEM,
        WarningSeverity.CRITICAL,
        "duplicate item",
    )
    offer = ComparisonOffer(uuid4(), "Acme", OfferStatus.MISSING, warnings=(critical,))
    item = ComparisonItem(
        comparison_id=uuid4(), product_id=uuid4(), requested_product_name="Sensor",
        requested_quantity=ComparisonQuantity(None, None), offers=(offer,),
        monetary_status=MonetaryComparisonStatus.INSUFFICIENT_DATA
    )
    comparison = Comparison(
        tender_id=uuid4(), catalog_snapshot_id=uuid4(), catalog_version=1,
        quotes_version="a" * 64, comparison_version="1.0", comparison_key="b" * 64,
        created_by_user_id=uuid4(), source_quote_ids=()
    )
    comparison.start()
    comparison.complete((item,), ())
    assert comparison.status is ComparisonStatus.INVALID
    comparison.archive()

    with pytest.raises(ValidationError):
        Comparison(
            tender_id=uuid4(), catalog_snapshot_id=uuid4(), catalog_version=0,
            quotes_version="a" * 64, comparison_version="1.0", comparison_key="b" * 64,
            created_by_user_id=uuid4(), source_quote_ids=()
        )
    with pytest.raises(ValidationError):
        Comparison(
            tender_id=uuid4(), catalog_snapshot_id=uuid4(), catalog_version=1,
            quotes_version="bad", comparison_version="1.0", comparison_key="b" * 64,
            created_by_user_id=uuid4(), source_quote_ids=()
        )
    with pytest.raises(ValidationError):
        Comparison(
            tender_id=uuid4(), catalog_snapshot_id=uuid4(), catalog_version=1,
            quotes_version="a" * 64, comparison_version=" ", comparison_key="b" * 64,
            created_by_user_id=uuid4(), source_quote_ids=()
        )
