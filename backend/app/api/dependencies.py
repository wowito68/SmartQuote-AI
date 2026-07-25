from functools import lru_cache

from app.application.ports.document_processing_queue import DocumentProcessingQueue
from app.application.ports.file_storage import FileStorage
from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.config.settings import get_settings
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.infrastructure.tasks.processing_queue import CeleryDocumentProcessingQueue


def get_uow_factory() -> UnitOfWorkFactory:
    return SqlAlchemyUnitOfWork


@lru_cache
def get_file_storage() -> FileStorage:
    return LocalFileStorage(get_settings().storage_root)


@lru_cache
def get_processing_queue() -> DocumentProcessingQueue:
    return CeleryDocumentProcessingQueue()
