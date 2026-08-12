from pathlib import Path
from uuid import uuid4

import pytest

from app.domain.documents.exceptions import DocumentStorageFailure
from app.infrastructure.storage.local_file_storage import LocalFileStorage


def test_local_storage_uses_private_uuid_path_and_round_trips(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path / "private")
    tender_id = uuid4()
    document_id = uuid4()
    key = storage.store(tender_id, document_id, b"%PDF-1.4\n%%EOF\n")

    assert key == f"tenders/{tender_id}/{document_id}.pdf"
    target = storage.root / key
    assert target.read_bytes() == b"%PDF-1.4\n%%EOF\n"
    assert target.stat().st_mode & 0o077 == 0
    assert storage.exists(key) is True
    assert storage.read(key).startswith(b"%PDF-")

    storage.delete(key)
    assert storage.exists(key) is False
    assert not target.exists()


def test_local_storage_rejects_path_traversal(tmp_path: Path) -> None:
    storage = LocalFileStorage(tmp_path / "private")
    with pytest.raises(DocumentStorageFailure):
        storage.read("../../secret.pdf")
    with pytest.raises(DocumentStorageFailure):
        storage.exists("../../secret.pdf")
    with pytest.raises(DocumentStorageFailure):
        storage.read("/tmp/secret.pdf")
