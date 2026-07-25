from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.api.dependencies import get_file_storage
from app.config.settings import Settings, get_settings
from app.infrastructure.db.models.audit_event import AuditEventModel
from app.infrastructure.db.models.tender import TenderModel
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.main import app

SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000001"
PDF_A = b"%PDF-1.4\nA document\n%%EOF\n"
PDF_B = b"%PDF-1.4\nB document\n%%EOF\n"


def create_tender(client: TestClient, title: str = "Document tender") -> str:
    response = client.post(
        "/api/v1/tenders",
        json={"title": title, "created_by_user_id": SYSTEM_USER_ID},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_document_endpoint_complete_flow_and_private_storage(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path / "private")
    app.dependency_overrides[get_file_storage] = lambda: storage
    client = TestClient(app)
    try:
        tender_id = create_tender(client)
        uploaded = client.post(
            f"/api/v1/tenders/{tender_id}/documents",
            data={"uploaded_by_user_id": SYSTEM_USER_ID},
            files=[
                ("files", ("bases.pdf", PDF_A, "application/pdf")),
                ("files", ("anexo.PDF", PDF_B, "application/pdf")),
            ],
        )
        assert uploaded.status_code == 201, uploaded.text
        body = uploaded.json()
        assert body["total"] == 2
        document_id = body["items"][0]["id"]
        UUID(document_id)
        assert body["items"][0]["status"] == "uploaded"
        assert len(body["items"][0]["file_hash"]) == 64

        stored_files = list(storage.root.rglob("*.pdf"))
        assert len(stored_files) == 2
        assert all(path.parent.name == tender_id for path in stored_files)
        assert {path.name for path in stored_files}.isdisjoint({"bases.pdf", "anexo.PDF"})

        listed = client.get(f"/api/v1/tenders/{tender_id}/documents")
        assert listed.status_code == 200
        assert listed.json()["total"] == 2

        metadata = client.get(f"/api/v1/documents/{document_id}")
        assert metadata.status_code == 200
        original_name = metadata.json()["original_file_name"]

        downloaded = client.get(f"/api/v1/documents/{document_id}/download")
        assert downloaded.status_code == 200
        assert downloaded.content in {PDF_A, PDF_B}
        assert downloaded.headers["content-type"] == "application/pdf"
        assert "attachment" in downloaded.headers["content-disposition"]
        assert original_name.replace(" ", "%20") in downloaded.headers["content-disposition"]
        assert downloaded.headers["x-content-type-options"] == "nosniff"

        deleted = client.delete(
            f"/api/v1/documents/{document_id}",
            params={"deleted_by_user_id": SYSTEM_USER_ID},
        )
        assert deleted.status_code == 204
        assert client.get(f"/api/v1/documents/{document_id}").status_code == 404
        assert client.get(f"/api/v1/documents/{document_id}/download").status_code == 404
        assert client.get(f"/api/v1/tenders/{tender_id}/documents").json()["total"] == 1
        assert len(list(storage.root.rglob("*.pdf"))) == 2

        second_delete = client.delete(
            f"/api/v1/documents/{document_id}",
            params={"deleted_by_user_id": SYSTEM_USER_ID},
        )
        assert second_delete.status_code == 409
        assert second_delete.json()["code"] == "document_already_deleted"

        with SessionLocal() as session:
            event_types = set(session.scalars(select(AuditEventModel.event_type)))
        assert {"DocumentUploaded", "DocumentDeleted"}.issubset(event_types)
    finally:
        app.dependency_overrides.clear()


def test_document_duplicate_and_validation_errors_are_mapped(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path / "private")
    app.dependency_overrides[get_file_storage] = lambda: storage
    client = TestClient(app)
    try:
        tender_id = create_tender(client, "Duplicate tender")
        first = client.post(
            f"/api/v1/tenders/{tender_id}/documents",
            data={"uploaded_by_user_id": SYSTEM_USER_ID},
            files={"files": ("bases.pdf", PDF_A, "application/pdf")},
        )
        assert first.status_code == 201

        duplicate = client.post(
            f"/api/v1/tenders/{tender_id}/documents",
            data={"uploaded_by_user_id": SYSTEM_USER_ID},
            files={"files": ("copy.pdf", PDF_A, "application/pdf")},
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["code"] == "duplicate_document"

        bad_extension = client.post(
            f"/api/v1/tenders/{tender_id}/documents",
            data={"uploaded_by_user_id": SYSTEM_USER_ID},
            files={"files": ("bases.txt", PDF_B, "application/pdf")},
        )
        assert bad_extension.status_code == 422
        assert bad_extension.json()["code"] == "invalid_document_file"

        bad_mime = client.post(
            f"/api/v1/tenders/{tender_id}/documents",
            data={"uploaded_by_user_id": SYSTEM_USER_ID},
            files={"files": ("bases.pdf", PDF_B, "text/plain")},
        )
        assert bad_mime.status_code == 422

        spoofed = client.post(
            f"/api/v1/tenders/{tender_id}/documents",
            data={"uploaded_by_user_id": SYSTEM_USER_ID},
            files={"files": ("bases.pdf", b"plain text", "application/pdf")},
        )
        assert spoofed.status_code == 422

        traversal = client.post(
            f"/api/v1/tenders/{tender_id}/documents",
            data={"uploaded_by_user_id": SYSTEM_USER_ID},
            files={"files": ("../bases.pdf", PDF_B, "application/pdf")},
        )
        assert traversal.status_code == 422

        unknown_user = client.post(
            f"/api/v1/tenders/{tender_id}/documents",
            data={"uploaded_by_user_id": "11111111-1111-1111-1111-111111111111"},
            files={"files": ("other.pdf", PDF_B, "application/pdf")},
        )
        assert unknown_user.status_code == 422
        assert unknown_user.json()["code"] == "document_user_not_found"

        with SessionLocal() as session:
            duplicates = session.scalars(
                select(AuditEventModel).where(
                    AuditEventModel.event_type == "DuplicateDocumentDetected"
                )
            ).all()
        assert len(duplicates) == 1
        assert duplicates[0].payload["file_hash"] == first.json()["items"][0]["file_hash"]
    finally:
        app.dependency_overrides.clear()


def test_document_size_count_and_tender_state_rules(tmp_path: Path) -> None:
    base_settings = get_settings()
    limited_settings = Settings(
        project_name=base_settings.project_name,
        version=base_settings.version,
        environment="test",
        api_v1_prefix=base_settings.api_v1_prefix,
        database_url=base_settings.database_url,
        storage_root=tmp_path / "private",
        max_document_size_bytes=16,
        max_documents_per_upload=1,
    )
    storage = LocalFileStorage(limited_settings.storage_root)
    app.dependency_overrides[get_file_storage] = lambda: storage
    app.dependency_overrides[get_settings] = lambda: limited_settings
    client = TestClient(app)
    try:
        tender_id = create_tender(client, "Limited tender")
        oversized = client.post(
            f"/api/v1/tenders/{tender_id}/documents",
            data={"uploaded_by_user_id": SYSTEM_USER_ID},
            files={"files": ("large.pdf", PDF_A + b"x" * 20, "application/pdf")},
        )
        assert oversized.status_code == 413
        assert oversized.json()["code"] == "document_too_large"

        too_many = client.post(
            f"/api/v1/tenders/{tender_id}/documents",
            data={"uploaded_by_user_id": SYSTEM_USER_ID},
            files=[
                ("files", ("a.pdf", b"%PDF-", "application/pdf")),
                ("files", ("b.pdf", b"%PDF-", "application/pdf")),
            ],
        )
        assert too_many.status_code == 422
        assert too_many.json()["code"] == "too_many_documents"

        archived_id = create_tender(client, "Archived tender")
        assert client.delete(f"/api/v1/tenders/{archived_id}").status_code == 204
        archived_upload = client.post(
            f"/api/v1/tenders/{archived_id}/documents",
            data={"uploaded_by_user_id": SYSTEM_USER_ID},
            files={"files": ("a.pdf", b"%PDF-", "application/pdf")},
        )
        assert archived_upload.status_code == 409
        assert archived_upload.json()["code"] == "tender_already_archived"

        closed_id = create_tender(client, "Closed tender")
        with SessionLocal.begin() as session:
            session.execute(
                update(TenderModel).where(TenderModel.id == UUID(closed_id)).values(status="closed")
            )
        closed_upload = client.post(
            f"/api/v1/tenders/{closed_id}/documents",
            data={"uploaded_by_user_id": SYSTEM_USER_ID},
            files={"files": ("a.pdf", b"%PDF-", "application/pdf")},
        )
        assert closed_upload.status_code == 409
        assert closed_upload.json()["code"] == "invalid_tender_state"
    finally:
        app.dependency_overrides.clear()
