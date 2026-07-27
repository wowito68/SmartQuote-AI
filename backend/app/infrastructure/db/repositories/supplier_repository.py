from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.application.ports.supplier_repository import SupplierRepository
from app.domain.suppliers.entities import (
    ProductSupplierMatch,
    Supplier,
    SupplierContact,
    SupplierDiscoveryRun,
    SupplierMergeSuggestion,
    SupplierSource,
    TenderSupplier,
)
from app.infrastructure.db.mappers.supplier_mapper import (
    contact_to_domain,
    contact_to_model,
    discovery_run_to_domain,
    discovery_run_to_model,
    match_to_domain,
    match_to_model,
    merge_suggestion_to_domain,
    merge_suggestion_to_model,
    source_to_domain,
    source_to_model,
    supplier_to_domain,
    supplier_to_model,
    tender_supplier_to_domain,
    tender_supplier_to_model,
    update_discovery_run_model,
    update_match_model,
    update_merge_suggestion_model,
    update_supplier_model,
    update_tender_supplier_model,
)
from app.infrastructure.db.models.supplier import (
    ProductSupplierMatchModel,
    SupplierContactModel,
    SupplierDiscoveryRunModel,
    SupplierMergeSuggestionModel,
    SupplierModel,
    SupplierSourceModel,
    TenderSupplierModel,
)


class SqlAlchemySupplierRepository(SupplierRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_run(self, run: SupplierDiscoveryRun) -> SupplierDiscoveryRun:
        model = discovery_run_to_model(run)
        self._session.add(model)
        self._session.flush()
        return discovery_run_to_domain(model)

    def update_run(self, run: SupplierDiscoveryRun) -> SupplierDiscoveryRun:
        model = self._session.get(SupplierDiscoveryRunModel, run.id)
        if model is None:
            raise ValueError("Supplier discovery run does not exist.")
        update_discovery_run_model(model, run)
        self._session.flush()
        return discovery_run_to_domain(model)

    def get_run(
        self, run_id: UUID, *, for_update: bool = False
    ) -> SupplierDiscoveryRun | None:
        statement = select(SupplierDiscoveryRunModel).where(
            SupplierDiscoveryRunModel.id == run_id
        )
        if for_update:
            statement = statement.with_for_update()
        model = self._session.scalars(statement).first()
        return discovery_run_to_domain(model) if model else None

    def get_run_by_idempotency(
        self, tender_id: UUID, key: str
    ) -> SupplierDiscoveryRun | None:
        statement = select(SupplierDiscoveryRunModel).where(
            SupplierDiscoveryRunModel.tender_id == tender_id,
            SupplierDiscoveryRunModel.idempotency_key == key,
        )
        model = self._session.scalars(statement).first()
        return discovery_run_to_domain(model) if model else None

    def list_runs(self, tender_id: UUID) -> list[SupplierDiscoveryRun]:
        statement = (
            select(SupplierDiscoveryRunModel)
            .where(SupplierDiscoveryRunModel.tender_id == tender_id)
            .order_by(SupplierDiscoveryRunModel.created_at)
        )
        return [discovery_run_to_domain(model) for model in self._session.scalars(statement)]

    def create_supplier(self, supplier: Supplier) -> Supplier:
        model = supplier_to_model(supplier)
        self._session.add(model)
        self._session.flush()
        return supplier_to_domain(model)

    def update_supplier(self, supplier: Supplier) -> Supplier:
        model = self._session.get(SupplierModel, supplier.id)
        if model is None:
            raise ValueError("Supplier does not exist.")
        update_supplier_model(model, supplier)
        self._session.flush()
        return supplier_to_domain(model)

    def get_supplier(self, supplier_id: UUID) -> Supplier | None:
        model = self._session.get(SupplierModel, supplier_id)
        return supplier_to_domain(model) if model else None

    def list_suppliers(self) -> list[Supplier]:
        statement = select(SupplierModel).order_by(SupplierModel.created_at, SupplierModel.id)
        return [supplier_to_domain(model) for model in self._session.scalars(statement)]

    def add_contact(self, contact: SupplierContact) -> SupplierContact:
        model = contact_to_model(contact)
        self._session.add(model)
        self._session.flush()
        return contact_to_domain(model)

    def list_contacts(self, supplier_id: UUID) -> list[SupplierContact]:
        statement = (
            select(SupplierContactModel)
            .where(SupplierContactModel.supplier_id == supplier_id)
            .order_by(SupplierContactModel.created_at, SupplierContactModel.id)
        )
        return [contact_to_domain(model) for model in self._session.scalars(statement)]

    def contact_exists(self, supplier_id: UUID, identity_key: str) -> bool:
        statement = select(SupplierContactModel.id).where(
            SupplierContactModel.supplier_id == supplier_id,
            SupplierContactModel.identity_key == identity_key,
        )
        return self._session.scalar(statement) is not None

    def add_source(self, source: SupplierSource) -> SupplierSource:
        model = source_to_model(source)
        self._session.add(model)
        self._session.flush()
        return source_to_domain(model)

    def list_sources(self, supplier_id: UUID) -> list[SupplierSource]:
        statement = (
            select(SupplierSourceModel)
            .where(SupplierSourceModel.supplier_id == supplier_id)
            .order_by(SupplierSourceModel.discovered_at, SupplierSourceModel.id)
        )
        return [source_to_domain(model) for model in self._session.scalars(statement)]

    def source_exists(self, supplier_id: UUID, source_url: str) -> bool:
        statement = select(SupplierSourceModel.id).where(
            SupplierSourceModel.supplier_id == supplier_id,
            SupplierSourceModel.source_url == source_url,
        )
        return self._session.scalar(statement) is not None

    def create_tender_supplier(self, tender_supplier: TenderSupplier) -> TenderSupplier:
        model = tender_supplier_to_model(tender_supplier)
        self._session.add(model)
        self._session.flush()
        return tender_supplier_to_domain(model)

    def update_tender_supplier(self, tender_supplier: TenderSupplier) -> TenderSupplier:
        model = self._session.get(TenderSupplierModel, tender_supplier.id)
        if model is None:
            raise ValueError("Tender supplier does not exist.")
        update_tender_supplier_model(model, tender_supplier)
        self._session.flush()
        return tender_supplier_to_domain(model)

    def get_tender_supplier(self, tender_supplier_id: UUID) -> TenderSupplier | None:
        model = self._session.get(TenderSupplierModel, tender_supplier_id)
        return tender_supplier_to_domain(model) if model else None

    def find_tender_supplier(
        self, tender_id: UUID, supplier_id: UUID
    ) -> TenderSupplier | None:
        statement = select(TenderSupplierModel).where(
            TenderSupplierModel.tender_id == tender_id,
            TenderSupplierModel.supplier_id == supplier_id,
        )
        model = self._session.scalars(statement).first()
        return tender_supplier_to_domain(model) if model else None

    def list_tender_suppliers(self, tender_id: UUID) -> list[TenderSupplier]:
        statement = (
            select(TenderSupplierModel)
            .where(TenderSupplierModel.tender_id == tender_id)
            .order_by(TenderSupplierModel.created_at, TenderSupplierModel.id)
        )
        return [
            tender_supplier_to_domain(model) for model in self._session.scalars(statement)
        ]

    def create_match(self, match: ProductSupplierMatch) -> ProductSupplierMatch:
        model = match_to_model(match)
        self._session.add(model)
        self._session.flush()
        return match_to_domain(model)

    def update_match(self, match: ProductSupplierMatch) -> ProductSupplierMatch:
        model = self._session.get(ProductSupplierMatchModel, match.id)
        if model is None:
            raise ValueError("Product supplier match does not exist.")
        update_match_model(model, match)
        self._session.flush()
        return match_to_domain(model)

    def get_match(
        self, tender_supplier_id: UUID, product_id: UUID
    ) -> ProductSupplierMatch | None:
        statement = select(ProductSupplierMatchModel).where(
            ProductSupplierMatchModel.tender_supplier_id == tender_supplier_id,
            ProductSupplierMatchModel.product_id == product_id,
        )
        model = self._session.scalars(statement).first()
        return match_to_domain(model) if model else None

    def list_matches(self, tender_supplier_id: UUID) -> list[ProductSupplierMatch]:
        statement = (
            select(ProductSupplierMatchModel)
            .where(ProductSupplierMatchModel.tender_supplier_id == tender_supplier_id)
            .order_by(ProductSupplierMatchModel.score.desc())
        )
        return [match_to_domain(model) for model in self._session.scalars(statement)]

    def create_merge_suggestion(
        self, suggestion: SupplierMergeSuggestion
    ) -> SupplierMergeSuggestion:
        model = merge_suggestion_to_model(suggestion)
        self._session.add(model)
        self._session.flush()
        return merge_suggestion_to_domain(model)

    def update_merge_suggestion(
        self, suggestion: SupplierMergeSuggestion
    ) -> SupplierMergeSuggestion:
        model = self._session.get(SupplierMergeSuggestionModel, suggestion.id)
        if model is None:
            raise ValueError("Supplier merge suggestion does not exist.")
        update_merge_suggestion_model(model, suggestion)
        self._session.flush()
        return merge_suggestion_to_domain(model)

    def get_merge_suggestion(
        self, suggestion_id: UUID
    ) -> SupplierMergeSuggestion | None:
        model = self._session.get(SupplierMergeSuggestionModel, suggestion_id)
        return merge_suggestion_to_domain(model) if model else None

    def find_merge_suggestion(
        self, source_supplier_id: UUID, target_supplier_id: UUID
    ) -> SupplierMergeSuggestion | None:
        statement = select(SupplierMergeSuggestionModel).where(
            SupplierMergeSuggestionModel.source_supplier_id == source_supplier_id,
            SupplierMergeSuggestionModel.target_supplier_id == target_supplier_id,
        )
        model = self._session.scalars(statement).first()
        return merge_suggestion_to_domain(model) if model else None

    def list_merge_suggestions(
        self, supplier_id: UUID
    ) -> list[SupplierMergeSuggestion]:
        statement = (
            select(SupplierMergeSuggestionModel)
            .where(
                or_(
                    SupplierMergeSuggestionModel.source_supplier_id == supplier_id,
                    SupplierMergeSuggestionModel.target_supplier_id == supplier_id,
                )
            )
            .order_by(SupplierMergeSuggestionModel.created_at)
        )
        return [
            merge_suggestion_to_domain(model) for model in self._session.scalars(statement)
        ]
