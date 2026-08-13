from app.infrastructure.db.models.audit_event import AuditEventModel
from app.infrastructure.db.models.catalog import (
    AIExtractionRunModel,
    CatalogProductModel,
    CatalogProductRevisionModel,
    CatalogSnapshotModel,
    EvidenceReferenceModel,
    ExtractedEvidenceModel,
)
from app.infrastructure.db.models.comparison import (
    ComparisonItemModel,
    ComparisonModel,
    ComparisonOfferModel,
)
from app.infrastructure.db.models.document_processing import (
    DocumentPageModel,
    DocumentQualityModel,
    ExtractionRunModel,
)
from app.infrastructure.db.models.quote import (
    ComparisonRunModel,
    QuoteDocumentModel,
    QuoteEvidenceReferenceModel,
    QuoteExtractionRunModel,
    QuoteItemModel,
    QuoteItemRevisionModel,
    QuoteModel,
    QuoteTaskRecordModel,
)
from app.infrastructure.db.models.quote_analysis import QuoteExtractionArtifactModel
from app.infrastructure.db.models.recommendation import RecommendationModel
from app.infrastructure.db.models.rfq import (
    EmailAttachmentModel,
    EmailMessageModel,
    OutboundMessageLogModel,
    RfqRequestModel,
    RfqTaskRecordModel,
    RfqVersionModel,
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
from app.infrastructure.db.models.tender import TenderDocumentModel, TenderModel
from app.infrastructure.db.models.user import UserModel

__all__ = [
    "AIExtractionRunModel",
    "AuditEventModel",
    "CatalogProductModel",
    "CatalogProductRevisionModel",
    "CatalogSnapshotModel",
    "ComparisonItemModel",
    "ComparisonModel",
    "ComparisonOfferModel",
    "ComparisonRunModel",
    "DocumentPageModel",
    "DocumentQualityModel",
    "EmailAttachmentModel",
    "EmailMessageModel",
    "EvidenceReferenceModel",
    "ExtractedEvidenceModel",
    "ExtractionRunModel",
    "OutboundMessageLogModel",
    "ProductSupplierMatchModel",
    "QuoteDocumentModel",
    "QuoteEvidenceReferenceModel",
    "QuoteExtractionArtifactModel",
    "QuoteExtractionRunModel",
    "QuoteItemModel",
    "QuoteItemRevisionModel",
    "QuoteModel",
    "QuoteTaskRecordModel",
    "RecommendationModel",
    "RfqRequestModel",
    "RfqTaskRecordModel",
    "RfqVersionModel",
    "SupplierContactModel",
    "SupplierDiscoveryRunModel",
    "SupplierMergeSuggestionModel",
    "SupplierModel",
    "SupplierSourceModel",
    "TenderDocumentModel",
    "TenderModel",
    "TenderSupplierModel",
    "UserModel",
]
