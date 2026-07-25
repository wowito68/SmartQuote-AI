import os
from pathlib import Path
from uuid import UUID, uuid4

from app.application.ports.file_storage import FileStorage
from app.domain.documents.exceptions import DocumentStorageFailure


class LocalFileStorage(FileStorage):
    def __init__(self, root: Path | str) -> None:
        self._root = Path(root).expanduser().resolve()
        self._root.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            self._root.chmod(0o700)
        except OSError:
            pass

    @property
    def root(self) -> Path:
        return self._root

    def _path_for_key(self, storage_key: str) -> Path:
        if not storage_key or "\\" in storage_key:
            raise DocumentStorageFailure("Invalid document storage key.")
        candidate = (self._root / storage_key).resolve()
        try:
            candidate.relative_to(self._root)
        except ValueError as exc:
            raise DocumentStorageFailure("Document storage key escapes the private root.") from exc
        return candidate

    def store(self, tender_id: UUID, document_id: UUID, content: bytes) -> str:
        storage_key = f"tenders/{tender_id}/{document_id}.pdf"
        target = self._path_for_key(storage_key)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.chmod(0o600)
            os.replace(temporary, target)
            target.chmod(0o600)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise DocumentStorageFailure("Unable to store the document securely.") from exc
        return storage_key

    def read(self, storage_key: str) -> bytes:
        target = self._path_for_key(storage_key)
        try:
            return target.read_bytes()
        except OSError as exc:
            raise DocumentStorageFailure("The stored document is unavailable.") from exc

    def delete(self, storage_key: str) -> None:
        target = self._path_for_key(storage_key)
        try:
            target.unlink(missing_ok=True)
        except OSError as exc:
            raise DocumentStorageFailure("Unable to remove the stored document.") from exc
