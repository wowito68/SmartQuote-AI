from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.ports.catalog_repository import CatalogRepository
from app.domain.catalog.entities import (
    AIExtractionRun,
    CatalogProduct,
    CatalogSnapshot,
    EvidenceReference,
    ExtractedEvidence,
)
from app.domain.catalog.value_objects import ProductStatus
from app.infrastructure.db.mappers.catalog_mapper import (
    ai_run_to_domain,
    ai_run_to_model,
    evidence_to_domain,
    evidence_to_models,
    product_to_domain,
    product_to_model,
    snapshot_to_domain,
    snapshot_to_model,
    update_ai_run_model,
    update_product_model,
)
from app.infrastructure.db.models.catalog import (
    AIExtractionRunModel,
    CatalogProductModel,
    CatalogProductRevisionModel,
    CatalogSnapshotModel,
    EvidenceReferenceModel,
    ExtractedEvidenceModel,
)


class SqlAlchemyCatalogRepository(CatalogRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_run(self, run: AIExtractionRun) -> AIExtractionRun:
        model = ai_run_to_model(run)
        self._session.add(model)
        self._session.flush()
        return ai_run_to_domain(model)

    def update_run(self, run: AIExtractionRun) -> AIExtractionRun:
        model = self._session.get(AIExtractionRunModel, run.id)
        if model is None:
            raise ValueError("AI extraction run does not exist.")
        update_ai_run_model(model, run)
        self._session.flush()
        return ai_run_to_domain(model)

    def get_run(self, run_id: UUID, *, for_update: bool = False) -> AIExtractionRun | None:
        statement = select(AIExtractionRunModel).where(AIExtractionRunModel.id == run_id)
        if for_update:
            statement = statement.with_for_update()
        model = self._session.scalars(statement).first()
        return ai_run_to_domain(model) if model else None

    def get_run_by_idempotency(self, document_id: UUID, key: str) -> AIExtractionRun | None:
        statement = select(AIExtractionRunModel).where(
            AIExtractionRunModel.document_id == document_id,
            AIExtractionRunModel.idempotency_key == key,
        )
        model = self._session.scalars(statement).first()
        return ai_run_to_domain(model) if model else None

    def list_runs(self, tender_id: UUID) -> list[AIExtractionRun]:
        statement = (
            select(AIExtractionRunModel)
            .where(AIExtractionRunModel.tender_id == tender_id)
            .order_by(AIExtractionRunModel.created_at)
        )
        return [ai_run_to_domain(model) for model in self._session.scalars(statement)]

    def create_product(self, product: CatalogProduct) -> CatalogProduct:
        model = product_to_model(product)
        self._session.add(model)
        self._session.flush()
        return product_to_domain(model)

    def update_product(self, product: CatalogProduct) -> CatalogProduct:
        model = self._session.get(CatalogProductModel, product.id)
        if model is None:
            raise ValueError("Catalog product does not exist.")
        update_product_model(model, product)
        self._session.flush()
        return product_to_domain(model)

    def get_product(self, product_id: UUID) -> CatalogProduct | None:
        model = self._session.get(CatalogProductModel, product_id)
        return product_to_domain(model) if model else None

    def list_products(self, tender_id: UUID) -> list[CatalogProduct]:
        statement = (
            select(CatalogProductModel)
            .where(CatalogProductModel.tender_id == tender_id)
            .order_by(CatalogProductModel.created_at, CatalogProductModel.id)
        )
        return [product_to_domain(model) for model in self._session.scalars(statement)]

    def list_products_by_run(self, run_id: UUID) -> list[CatalogProduct]:
        statement = (
            select(CatalogProductModel)
            .where(CatalogProductModel.ai_extraction_run_id == run_id)
            .order_by(CatalogProductModel.created_at, CatalogProductModel.id)
        )
        return [product_to_domain(model) for model in self._session.scalars(statement)]

    def list_products_by_status(
        self, tender_id: UUID, statuses: set[ProductStatus]
    ) -> list[CatalogProduct]:
        statement = select(CatalogProductModel).where(
            CatalogProductModel.tender_id == tender_id,
            CatalogProductModel.status.in_([status.value for status in statuses]),
        )
        return [product_to_domain(model) for model in self._session.scalars(statement)]

    def add_revision(
        self,
        product_id: UUID,
        changed_by_user_id: UUID,
        before: dict,
        after: dict,
        changed_fields: list[str],
    ) -> None:
        self._session.add(
            CatalogProductRevisionModel(
                id=uuid4(),
                product_id=product_id,
                changed_by_user_id=changed_by_user_id,
                before_payload=before,
                after_payload=after,
                changed_fields=changed_fields,
            )
        )
        self._session.flush()

    def add_evidence(
        self, evidence: ExtractedEvidence, reference: EvidenceReference
    ) -> None:
        evidence_model, reference_model = evidence_to_models(evidence, reference)
        self._session.add(evidence_model)
        self._session.flush()
        self._session.add(reference_model)
        self._session.flush()

    def list_evidence(
        self, product_id: UUID
    ) -> list[tuple[ExtractedEvidence, EvidenceReference]]:
        statement = (
            select(ExtractedEvidenceModel, EvidenceReferenceModel)
            .join(
                EvidenceReferenceModel,
                EvidenceReferenceModel.evidence_id == ExtractedEvidenceModel.id,
            )
            .where(ExtractedEvidenceModel.product_id == product_id)
            .order_by(ExtractedEvidenceModel.page_number, ExtractedEvidenceModel.created_at)
        )
        return [
            evidence_to_domain(evidence, reference)
            for evidence, reference in self._session.execute(statement)
        ]

    def create_snapshot(self, snapshot: CatalogSnapshot) -> CatalogSnapshot:
        model = snapshot_to_model(snapshot)
        self._session.add(model)
        self._session.flush()
        return snapshot_to_domain(model)

    def get_latest_snapshot(self, tender_id: UUID) -> CatalogSnapshot | None:
        statement = (
            select(CatalogSnapshotModel)
            .where(CatalogSnapshotModel.tender_id == tender_id)
            .order_by(CatalogSnapshotModel.version.desc())
        )
        model = self._session.scalars(statement).first()
        return snapshot_to_domain(model) if model else None
