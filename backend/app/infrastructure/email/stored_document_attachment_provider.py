import hashlib
from uuid import UUID

from app.application.ports.attachment_provider import AttachmentContent, AttachmentProvider
from app.application.ports.file_storage import FileStorage
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.domain.documents.exceptions import DocumentStorageFailure
from app.domain.rfqs.entities import EmailAttachment
from app.domain.rfqs.exceptions import AttachmentValidationError


class StoredDocumentAttachmentProvider(AttachmentProvider):
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        file_storage: FileStorage,
        max_total_bytes: int = 25 * 1024 * 1024,
    ) -> None:
        self._uow_factory = uow_factory
        self._file_storage = file_storage
        self._max_total_bytes = max_total_bytes

    def build_metadata(
        self,
        tender_id: UUID,
        rfq_id: UUID,
        document_ids: tuple[UUID, ...] | None,
    ) -> tuple[EmailAttachment, ...]:
        with self._uow_factory() as uow:
            if document_ids is None:
                documents = uow.documents.list_by_tender(tender_id)
            else:
                documents = []
                seen: set[UUID] = set()
                for document_id in document_ids:
                    if document_id in seen:
                        continue
                    seen.add(document_id)
                    document = uow.documents.get_by_id(document_id)
                    if document is None or document.tender_id != tender_id:
                        raise AttachmentValidationError(
                            "Attachment document does not exist in the RFQ tender."
                        )
                    documents.append(document)
        if sum(document.file_size for document in documents) > self._max_total_bytes:
            raise AttachmentValidationError("RFQ attachments exceed the configured total size.")
        return tuple(
            EmailAttachment(
                rfq_id=rfq_id,
                document_id=document.id,
                original_file_name=document.original_file_name,
                file_hash=document.file_hash.value,
                file_size=document.file_size,
                mime_type=document.mime_type,
            )
            for document in documents
        )

    def load(self, attachments: tuple[EmailAttachment, ...]) -> tuple[AttachmentContent, ...]:
        result: list[AttachmentContent] = []
        with self._uow_factory() as uow:
            for attachment in attachments:
                document = uow.documents.get_by_id(attachment.document_id)
                if document is None:
                    raise AttachmentValidationError("RFQ attachment document is unavailable.")
                if document.file_hash.value != attachment.file_hash:
                    raise AttachmentValidationError("RFQ attachment hash no longer matches metadata.")
                try:
                    content = self._file_storage.read(document.storage_key)
                except DocumentStorageFailure as exc:
                    raise AttachmentValidationError("RFQ attachment content is unavailable.") from exc
                if len(content) != attachment.file_size:
                    raise AttachmentValidationError("RFQ attachment size no longer matches metadata.")
                if hashlib.sha256(content).hexdigest() != attachment.file_hash:
                    raise AttachmentValidationError("RFQ attachment content failed SHA-256 validation.")
                result.append(AttachmentContent(attachment, content))
        return tuple(result)
