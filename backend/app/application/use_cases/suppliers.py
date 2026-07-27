from typing import Any
from uuid import UUID

from app.application.dtos.suppliers import (
    ManualSupplierCommand,
    ProductSupplierMatchResponse,
    SupplierContactResponse,
    SupplierDiscoveryRunResponse,
    SupplierMergeSuggestionResponse,
    SupplierMetricsResponse,
    SupplierSourceResponse,
    SupplierUpdateCommand,
    TenderSupplierResponse,
    TenderSuppliersResponse,
)
from app.application.exceptions import TenderNotFound
from app.application.ports.supplier_search_service import (
    SupplierContactSuggestion,
    SupplierSuggestion,
)
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.application.services.supplier_deduplication import SupplierDeduplicationService
from app.domain.suppliers.entities import (
    ProductSupplierMatch,
    Supplier,
    SupplierContact,
    SupplierMergeSuggestion,
    SupplierSource,
    TenderSupplier,
)
from app.domain.suppliers.events import supplier_event
from app.domain.suppliers.exceptions import (
    InvalidSupplierState,
    SupplierMergeConflict,
    SupplierNotFound,
)
from app.domain.suppliers.value_objects import (
    MergeSuggestionStatus,
    SupplierConfidence,
    SupplierMatchScore,
    SupplierStatus,
)


def _run_response(run) -> SupplierDiscoveryRunResponse:
    return SupplierDiscoveryRunResponse(
        id=run.id,
        tender_id=run.tender_id,
        catalog_snapshot_id=run.catalog_snapshot_id,
        status=run.status,
        current_stage=run.current_stage,
        search_provider=run.search_provider,
        search_provider_version=run.search_provider_version,
        matching_algorithm_version=run.matching_algorithm_version,
        reused=run.reused_from_run_id is not None,
        created_at=run.created_at,
    )


def _supplier_payload(supplier: Supplier) -> dict[str, Any]:
    return {
        "supplier_id": str(supplier.id),
        "legal_name": supplier.legal_name,
        "trade_name": supplier.trade_name,
        "website": supplier.website,
        "normalized_domain": supplier.normalized_domain,
        "category": supplier.category,
        "country": supplier.country,
        "city": supplier.city,
        "description": supplier.description,
        "merged_into_supplier_id": (
            str(supplier.merged_into_supplier_id)
            if supplier.merged_into_supplier_id
            else None
        ),
    }


def _response(uow, item: TenderSupplier) -> TenderSupplierResponse:
    supplier = uow.suppliers.get_supplier(item.supplier_id)
    if supplier is None:
        raise SupplierNotFound("Supplier master was not found.")
    contacts = tuple(
        SupplierContactResponse(
            id=contact.id,
            contact_type=contact.contact_type,
            value=contact.value,
            confidence=contact.confidence.value,
            source_url=contact.source_url,
            contact_name=contact.contact_name,
            role=contact.role,
            created_at=contact.created_at,
        )
        for contact in uow.suppliers.list_contacts(supplier.id)
    )
    sources = tuple(
        SupplierSourceResponse(
            id=source.id,
            provider_name=source.provider_name,
            source_type=source.source_type,
            source_url=source.source_url,
            source_title=source.source_title,
            excerpt=source.excerpt,
            discovered_at=source.discovered_at,
        )
        for source in uow.suppliers.list_sources(supplier.id)
    )
    matches = tuple(
        ProductSupplierMatchResponse(
            id=match.id,
            product_id=match.product_id,
            score=match.score.value,
            components=match.components,
            reasons=match.reasons,
            algorithm_version=match.algorithm_version,
        )
        for match in uow.suppliers.list_matches(item.id)
    )
    suggestions = tuple(
        SupplierMergeSuggestionResponse(
            id=suggestion.id,
            source_supplier_id=suggestion.source_supplier_id,
            target_supplier_id=suggestion.target_supplier_id,
            score=suggestion.score.value,
            signals=suggestion.signals,
            status=suggestion.status,
        )
        for suggestion in uow.suppliers.list_merge_suggestions(supplier.id)
    )
    return TenderSupplierResponse(
        id=item.id,
        tender_id=item.tender_id,
        supplier_id=supplier.id,
        discovery_run_id=item.discovery_run_id,
        status=item.status,
        is_manual=item.is_manual,
        legal_name=supplier.legal_name,
        trade_name=supplier.trade_name,
        website=supplier.website,
        normalized_domain=supplier.normalized_domain,
        category=supplier.category,
        country=supplier.country,
        city=supplier.city,
        description=supplier.description,
        merged_into_supplier_id=supplier.merged_into_supplier_id,
        merged_into_tender_supplier_id=item.merged_into_tender_supplier_id,
        reviewed_by_user_id=item.reviewed_by_user_id,
        reviewed_at=item.reviewed_at,
        rejection_reason=item.rejection_reason,
        contacts=contacts,
        sources=sources,
        matches=matches,
        merge_suggestions=suggestions,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


class GetTenderSuppliers:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, tender_id: UUID) -> TenderSuppliersResponse:
        with self._uow_factory() as uow:
            if uow.tenders.get_by_id(tender_id) is None:
                raise TenderNotFound("Tender was not found.")
            items = uow.suppliers.list_tender_suppliers(tender_id)
            responses = tuple(_response(uow, item) for item in items)
            runs = uow.suppliers.list_runs(tender_id)
        total = len(items)
        approved = sum(item.status is SupplierStatus.APPROVED for item in items)
        rejected = sum(item.status is SupplierStatus.REJECTED for item in items)
        merged = sum(item.status is SupplierStatus.MERGED for item in items)
        pending = sum(item.status is SupplierStatus.PENDING_REVIEW for item in items)
        valid_contacts = sum(bool(response.contacts) for response in responses)
        duplicates = sum(run.duplicates_detected for run in runs)
        search_durations = [
            run.search_duration_ms for run in runs if run.search_duration_ms is not None
        ]
        matching_durations = [
            run.matching_duration_ms for run in runs if run.matching_duration_ms is not None
        ]
        metrics = SupplierMetricsResponse(
            suppliers_total=total,
            suppliers_pending_review=pending,
            suppliers_approved=approved,
            suppliers_rejected=rejected,
            suppliers_merged=merged,
            duplicates_detected=duplicates,
            suppliers_with_valid_contact=valid_contacts,
            valid_contact_percentage=(round(valid_contacts / total * 100, 2) if total else 0.0),
            approval_percentage=(round(approved / total * 100, 2) if total else 0.0),
            average_search_duration_ms=(
                round(sum(search_durations) / len(search_durations), 2)
                if search_durations
                else 0.0
            ),
            average_matching_duration_ms=(
                round(sum(matching_durations) / len(matching_durations), 2)
                if matching_durations
                else 0.0
            ),
            provider_error_count=sum(len(run.provider_errors) for run in runs),
        )
        return TenderSuppliersResponse(
            tender_id=tender_id,
            suppliers=responses,
            discovery_runs=tuple(_run_response(run) for run in runs),
            metrics=metrics,
        )


class GetSupplier:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, tender_supplier_id: UUID) -> TenderSupplierResponse:
        with self._uow_factory() as uow:
            item = uow.suppliers.get_tender_supplier(tender_supplier_id)
            if item is None:
                raise SupplierNotFound("Tender supplier was not found.")
            return _response(uow, item)


class UpdateSupplier:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(
        self, tender_supplier_id: UUID, command: SupplierUpdateCommand
    ) -> TenderSupplierResponse:
        with self._uow_factory() as uow:
            item = uow.suppliers.get_tender_supplier(tender_supplier_id)
            if item is None:
                raise SupplierNotFound("Tender supplier was not found.")
            if item.status is not SupplierStatus.PENDING_REVIEW:
                raise InvalidSupplierState("Only pending-review suppliers can be edited.")
            if not uow.users.exists(command.changed_by_user_id):
                raise InvalidSupplierState("Supplier reviewer was not found.")
            supplier = uow.suppliers.get_supplier(item.supplier_id)
            if supplier is None:
                raise SupplierNotFound("Supplier master was not found.")
            before = _supplier_payload(supplier)
            supplier.edit(
                legal_name=command.legal_name,
                trade_name=command.trade_name,
                website=command.website,
                category=command.category,
                country=command.country,
                city=command.city,
                description=command.description,
            )
            supplier = uow.suppliers.update_supplier(supplier)
            for input_contact in command.contacts:
                contact = SupplierContact(
                    supplier_id=supplier.id,
                    contact_type=input_contact.contact_type,
                    value=input_contact.value,
                    confidence=SupplierConfidence(input_contact.confidence),
                    source_url=input_contact.source_url,
                    contact_name=input_contact.contact_name,
                    role=input_contact.role,
                )
                if not uow.suppliers.contact_exists(supplier.id, contact.identity_key):
                    uow.suppliers.add_contact(contact)
            after = _supplier_payload(supplier)
            changed_fields = sorted(
                key for key in before if before.get(key) != after.get(key)
            )
            if command.contacts:
                changed_fields.append("contacts")
            uow.audit_events.append(
                supplier_event(
                    item.id,
                    "SupplierUpdated",
                    tender_id=str(item.tender_id),
                    supplier_id=str(supplier.id),
                    changed_by_user_id=str(command.changed_by_user_id),
                    changed_fields=changed_fields,
                    before=before,
                    after=after,
                )
            )
            uow.commit()
            return _response(uow, item)


class ApproveSupplier:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(
        self, tender_supplier_id: UUID, reviewer_user_id: UUID
    ) -> TenderSupplierResponse:
        with self._uow_factory() as uow:
            item = uow.suppliers.get_tender_supplier(tender_supplier_id)
            if item is None:
                raise SupplierNotFound("Tender supplier was not found.")
            if not uow.users.exists(reviewer_user_id):
                raise InvalidSupplierState("Supplier reviewer was not found.")
            item.approve(reviewer_user_id)
            item = uow.suppliers.update_tender_supplier(item)
            uow.audit_events.append(
                supplier_event(
                    item.id,
                    "SupplierApproved",
                    tender_id=str(item.tender_id),
                    supplier_id=str(item.supplier_id),
                    reviewer_user_id=str(reviewer_user_id),
                )
            )
            uow.commit()
            return _response(uow, item)


class RejectSupplier:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(
        self,
        tender_supplier_id: UUID,
        reviewer_user_id: UUID,
        reason: str,
    ) -> TenderSupplierResponse:
        with self._uow_factory() as uow:
            item = uow.suppliers.get_tender_supplier(tender_supplier_id)
            if item is None:
                raise SupplierNotFound("Tender supplier was not found.")
            if not uow.users.exists(reviewer_user_id):
                raise InvalidSupplierState("Supplier reviewer was not found.")
            item.reject(reviewer_user_id, reason)
            item = uow.suppliers.update_tender_supplier(item)
            uow.audit_events.append(
                supplier_event(
                    item.id,
                    "SupplierRejected",
                    tender_id=str(item.tender_id),
                    supplier_id=str(item.supplier_id),
                    reviewer_user_id=str(reviewer_user_id),
                    reason=item.rejection_reason,
                )
            )
            uow.commit()
            return _response(uow, item)


class MergeSuppliers:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(
        self,
        source_tender_supplier_id: UUID,
        target_tender_supplier_id: UUID,
        reviewer_user_id: UUID,
        *,
        suggestion_id: UUID | None = None,
    ) -> TenderSupplierResponse:
        with self._uow_factory() as uow:
            source_item = uow.suppliers.get_tender_supplier(source_tender_supplier_id)
            target_item = uow.suppliers.get_tender_supplier(target_tender_supplier_id)
            if source_item is None or target_item is None:
                raise SupplierNotFound("Supplier to merge was not found.")
            if source_item.tender_id != target_item.tender_id:
                raise SupplierMergeConflict("Suppliers must belong to the same tender.")
            if target_item.status in {SupplierStatus.REJECTED, SupplierStatus.MERGED}:
                raise SupplierMergeConflict("Target supplier is not eligible for merging.")
            if not uow.users.exists(reviewer_user_id):
                raise InvalidSupplierState("Supplier reviewer was not found.")
            source = uow.suppliers.get_supplier(source_item.supplier_id)
            target = uow.suppliers.get_supplier(target_item.supplier_id)
            if source is None or target is None:
                raise SupplierNotFound("Supplier master was not found.")

            for contact in uow.suppliers.list_contacts(source.id):
                clone = SupplierContact(
                    supplier_id=target.id,
                    contact_type=contact.contact_type,
                    value=contact.value,
                    confidence=contact.confidence,
                    source_url=contact.source_url,
                    contact_name=contact.contact_name,
                    role=contact.role,
                )
                if not uow.suppliers.contact_exists(target.id, clone.identity_key):
                    uow.suppliers.add_contact(clone)
            for source_record in uow.suppliers.list_sources(source.id):
                if not uow.suppliers.source_exists(target.id, source_record.source_url):
                    uow.suppliers.add_source(
                        SupplierSource(
                            supplier_id=target.id,
                            provider_name=source_record.provider_name,
                            source_type=source_record.source_type,
                            source_url=source_record.source_url,
                            source_title=source_record.source_title,
                            excerpt=source_record.excerpt,
                            discovered_at=source_record.discovered_at,
                        )
                    )
            for match in uow.suppliers.list_matches(source_item.id):
                target_match = uow.suppliers.get_match(target_item.id, match.product_id)
                if target_match is None:
                    uow.suppliers.create_match(
                        ProductSupplierMatch(
                            tender_supplier_id=target_item.id,
                            product_id=match.product_id,
                            score=match.score,
                            components=match.components,
                            reasons=match.reasons,
                            algorithm_version=match.algorithm_version,
                        )
                    )
                elif match.score.value > target_match.score.value:
                    uow.suppliers.update_match(
                        ProductSupplierMatch(
                            id=target_match.id,
                            tender_supplier_id=target_item.id,
                            product_id=match.product_id,
                            score=SupplierMatchScore(match.score.value),
                            components=match.components,
                            reasons=match.reasons,
                            algorithm_version=match.algorithm_version,
                            created_at=target_match.created_at,
                        )
                    )

            source.merge_into(target.id)
            uow.suppliers.update_supplier(source)
            source_item.merge_into(target_item.id, reviewer_user_id)
            source_item = uow.suppliers.update_tender_supplier(source_item)
            if suggestion_id is not None:
                suggestion = uow.suppliers.get_merge_suggestion(suggestion_id)
                if suggestion is None:
                    raise SupplierMergeConflict("Merge suggestion was not found.")
                if {
                    suggestion.source_supplier_id,
                    suggestion.target_supplier_id,
                } != {source.id, target.id}:
                    raise SupplierMergeConflict("Merge suggestion does not match suppliers.")
                suggestion.accept(reviewer_user_id)
                uow.suppliers.update_merge_suggestion(suggestion)
            else:
                suggestion = uow.suppliers.find_merge_suggestion(source.id, target.id)
                if suggestion and suggestion.status is MergeSuggestionStatus.PENDING:
                    suggestion.accept(reviewer_user_id)
                    uow.suppliers.update_merge_suggestion(suggestion)
            uow.audit_events.append(
                supplier_event(
                    source_item.id,
                    "SupplierMerged",
                    tender_id=str(source_item.tender_id),
                    source_supplier_id=str(source.id),
                    target_supplier_id=str(target.id),
                    source_tender_supplier_id=str(source_item.id),
                    target_tender_supplier_id=str(target_item.id),
                    reviewer_user_id=str(reviewer_user_id),
                )
            )
            uow.commit()
            return _response(uow, source_item)


class CreateManualSupplier:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        deduplication_service: SupplierDeduplicationService,
    ) -> None:
        self._uow_factory = uow_factory
        self._deduplication_service = deduplication_service

    def execute(self, command: ManualSupplierCommand) -> TenderSupplierResponse:
        suggestion = SupplierSuggestion(
            legal_name=command.legal_name,
            trade_name=command.trade_name,
            website=command.website,
            category=command.category,
            country=command.country,
            city=command.city,
            description=command.description,
            source_url=f"manual://user/{command.created_by_user_id}",
            source_title="Manual supplier entry",
            source_type="manual",
            source_excerpt=command.source_note,
            contacts=tuple(
                SupplierContactSuggestion(
                    contact_type=contact.contact_type.value,
                    value=contact.value,
                    confidence=contact.confidence,
                    source_url=contact.source_url,
                    contact_name=contact.contact_name,
                    role=contact.role,
                )
                for contact in command.contacts
            ),
        )
        with self._uow_factory() as uow:
            if uow.tenders.get_by_id(command.tender_id) is None:
                raise TenderNotFound("Tender was not found.")
            if not uow.users.exists(command.created_by_user_id):
                raise InvalidSupplierState("Supplier creator was not found.")
            suppliers = uow.suppliers.list_suppliers()
            contacts_by_supplier = {
                supplier.id: uow.suppliers.list_contacts(supplier.id)
                for supplier in suppliers
            }
            duplicate = self._deduplication_service.find_best(
                suggestion,
                suppliers,
                contacts_by_supplier,
            )
            if duplicate and duplicate.exact_identity:
                supplier = uow.suppliers.get_supplier(duplicate.supplier_id)
                if supplier is None:
                    raise SupplierNotFound("Matching supplier was not found.")
            else:
                supplier = uow.suppliers.create_supplier(
                    Supplier(
                        legal_name=command.legal_name,
                        trade_name=command.trade_name,
                        website=command.website,
                        category=command.category,
                        country=command.country,
                        city=command.city,
                        description=command.description,
                    )
                )
                if (
                    duplicate
                    and duplicate.score
                    >= self._deduplication_service.suggestion_threshold
                ):
                    uow.suppliers.create_merge_suggestion(
                        SupplierMergeSuggestion(
                            source_supplier_id=supplier.id,
                            target_supplier_id=duplicate.supplier_id,
                            score=SupplierConfidence(duplicate.score),
                            signals=duplicate.signals,
                        )
                    )
            if not uow.suppliers.source_exists(supplier.id, suggestion.source_url):
                uow.suppliers.add_source(
                    SupplierSource(
                        supplier_id=supplier.id,
                        provider_name="manual",
                        source_type="manual",
                        source_url=suggestion.source_url,
                        source_title=suggestion.source_title,
                        excerpt=suggestion.source_excerpt,
                    )
                )
            for input_contact in command.contacts:
                contact = SupplierContact(
                    supplier_id=supplier.id,
                    contact_type=input_contact.contact_type,
                    value=input_contact.value,
                    confidence=SupplierConfidence(input_contact.confidence),
                    source_url=input_contact.source_url,
                    contact_name=input_contact.contact_name,
                    role=input_contact.role,
                )
                if not uow.suppliers.contact_exists(supplier.id, contact.identity_key):
                    uow.suppliers.add_contact(contact)
            item = uow.suppliers.find_tender_supplier(command.tender_id, supplier.id)
            if item is None:
                item = TenderSupplier(
                    tender_id=command.tender_id,
                    supplier_id=supplier.id,
                    is_manual=True,
                )
                item.mark_contact_discovery_complete()
                item.start_review()
                item = uow.suppliers.create_tender_supplier(item)
            uow.audit_events.append(
                supplier_event(
                    item.id,
                    "ManualSupplierCreated",
                    tender_id=str(command.tender_id),
                    supplier_id=str(supplier.id),
                    created_by_user_id=str(command.created_by_user_id),
                    duplicate_score=duplicate.score if duplicate else 0.0,
                )
            )
            uow.commit()
            return _response(uow, item)
