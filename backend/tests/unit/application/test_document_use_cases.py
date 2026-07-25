from copy import deepcopy
from types import TracebackType
from uuid import UUID, uuid4

import pytest

from app.application.dtos.document import UploadDocumentFile, UploadTenderDocumentRequest
from app.application.ports.unit_of_work import UnitOfWork
from app.application.use_cases.documents import (
    DeleteTenderDocument,
    DownloadTenderDocument,
    GetTenderDocument,
    ListTenderDocuments,
    UploadTenderDocument,
)
from app.domain.documents.entities import TenderDocument
from app.domain.documents.events import (
    DocumentDeleted,
    DocumentUploaded,
    DuplicateDocumentDetected,
)
from app.domain.documents.exceptions import (
    DocumentAlreadyDeleted,
    DocumentNotFound,
    DuplicateDocument,
)
from app.domain.documents.value_objects import FileHash
from app.domain.tenders.entities import Tender
from app.domain.tenders.value_objects import TenderStatus

PDF_A = b"%PDF-1.4\nA\n%%EOF\n"
PDF_B = b"%PDF-1.4\nB\n%%EOF\n"


class FakeTenderRepository:
    def __init__(self, storage: dict[UUID, Tender]) -> None:
        self.storage = storage

    def get_by_id(self, tender_id: UUID, *, include_archived: bool = False):
        tender = self.storage.get(tender_id)
        if tender is None or (tender.is_deleted and not include_archived):
            return None
        return deepcopy(tender)

    def update(self, tender: Tender) -> Tender:
        self.storage[tender.id] = deepcopy(tender)
        return deepcopy(tender)


class FakeDocumentRepository:
    def __init__(self, storage: dict[UUID, TenderDocument]) -> None:
        self.storage = storage
        self.fail_after: int | None = None
        self.created_count = 0

    def create(self, document: TenderDocument) -> TenderDocument:
        self.created_count += 1
        if self.fail_after == self.created_count:
            raise RuntimeError("database failure")
        self.storage[document.id] = deepcopy(document)
        return deepcopy(document)

    def get_by_id(self, document_id: UUID, *, include_deleted: bool = False):
        document = self.storage.get(document_id)
        if document is None or (document.is_deleted and not include_deleted):
            return None
        return deepcopy(document)

    def list_by_tender(self, tender_id: UUID) -> list[TenderDocument]:
        return [
            deepcopy(document)
            for document in self.storage.values()
            if document.tender_id == tender_id and not document.is_deleted
        ]

    def find_by_hash(
        self,
        tender_id: UUID,
        file_hash: FileHash,
        *,
        include_deleted: bool = True,
    ):
        for document in self.storage.values():
            if document.tender_id != tender_id or document.file_hash != file_hash:
                continue
            if document.is_deleted and not include_deleted:
                continue
            return deepcopy(document)
        return None

    def update(self, document: TenderDocument) -> TenderDocument:
        self.storage[document.id] = deepcopy(document)
        return deepcopy(document)


class FakeAuditRepository:
    def __init__(self, events: list[object]) -> None:
        self.events = events

    def append(self, event: object) -> None:
        self.events.append(event)


class FakeUserLookup:
    def __init__(self, users: set[UUID]) -> None:
        self.users = users

    def exists(self, user_id: UUID) -> bool:
        return user_id in self.users


class FakeUnitOfWork(UnitOfWork):
    def __init__(self, context: dict[str, object]) -> None:
        self.tenders = FakeTenderRepository(context["tenders"])
        self.documents = FakeDocumentRepository(context["documents"])
        self.documents.fail_after = context.get("fail_after")
        self.audit_events = FakeAuditRepository(context["events"])
        self.users = FakeUserLookup(context["users"])
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type:
            self.rollback()

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


class FakeFileStorage:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.deleted: list[str] = []

    def store(self, tender_id: UUID, document_id: UUID, content: bytes) -> str:
        key = f"tenders/{tender_id}/{document_id}.pdf"
        self.files[key] = content
        return key

    def read(self, storage_key: str) -> bytes:
        return self.files[storage_key]

    def delete(self, storage_key: str) -> None:
        self.deleted.append(storage_key)
        self.files.pop(storage_key, None)


@pytest.fixture()
def context():
    user_id = uuid4()
    tender = Tender(title="Tender", created_by_user_id=user_id)
    state: dict[str, object] = {
        "tenders": {tender.id: tender},
        "documents": {},
        "events": [],
        "users": {user_id},
    }

    def factory() -> FakeUnitOfWork:
        return FakeUnitOfWork(state)

    return state, user_id, tender, factory


def request(user_id: UUID, *files: tuple[str, bytes]) -> UploadTenderDocumentRequest:
    return UploadTenderDocumentRequest(
        uploaded_by_user_id=user_id,
        files=tuple(
            UploadDocumentFile(name, "application/pdf", content) for name, content in files
        ),
    )


def test_upload_get_list_download_and_delete_document(context) -> None:
    state, user_id, tender, factory = context
    storage = FakeFileStorage()
    uploaded = UploadTenderDocument(
        factory,
        storage,
        maximum_size_bytes=1024,
        maximum_files_per_upload=5,
    ).execute(
        tender.id,
        request(user_id, ("a.pdf", PDF_A), ("b.pdf", PDF_B)),
    )

    assert uploaded.total == 2
    assert state["tenders"][tender.id].status is TenderStatus.DOCUMENTS_PENDING
    assert sum(isinstance(event, DocumentUploaded) for event in state["events"]) == 2

    document_id = uploaded.items[0].id
    assert GetTenderDocument(factory).execute(document_id).id == document_id
    assert ListTenderDocuments(factory).execute(tender.id).total == 2
    downloaded = DownloadTenderDocument(factory, storage).execute(document_id)
    assert downloaded.content in {PDF_A, PDF_B}

    DeleteTenderDocument(factory).execute(document_id, user_id)
    assert isinstance(state["events"][-1], DocumentDeleted)
    with pytest.raises(DocumentNotFound):
        GetTenderDocument(factory).execute(document_id)
    with pytest.raises(DocumentAlreadyDeleted):
        DeleteTenderDocument(factory).execute(document_id, user_id)


def test_duplicate_detection_is_audited_for_existing_and_request_duplicates(context) -> None:
    state, user_id, tender, factory = context
    storage = FakeFileStorage()
    use_case = UploadTenderDocument(
        factory,
        storage,
        maximum_size_bytes=1024,
        maximum_files_per_upload=5,
    )
    use_case.execute(tender.id, request(user_id, ("a.pdf", PDF_A)))

    with pytest.raises(DuplicateDocument):
        use_case.execute(tender.id, request(user_id, ("copy.pdf", PDF_A)))
    assert isinstance(state["events"][-1], DuplicateDocumentDetected)

    state["documents"].clear()
    with pytest.raises(DuplicateDocument):
        use_case.execute(
            tender.id,
            request(user_id, ("a.pdf", PDF_B), ("copy.pdf", PDF_B)),
        )
    assert isinstance(state["events"][-1], DuplicateDocumentDetected)


def test_upload_compensates_file_storage_when_database_fails(context) -> None:
    state, user_id, tender, factory = context
    state["fail_after"] = 2
    storage = FakeFileStorage()
    with pytest.raises(RuntimeError):
        UploadTenderDocument(
            factory,
            storage,
            maximum_size_bytes=1024,
            maximum_files_per_upload=5,
        ).execute(
            tender.id,
            request(user_id, ("a.pdf", PDF_A), ("b.pdf", PDF_B)),
        )
    assert storage.files == {}
    assert len(storage.deleted) == 2
