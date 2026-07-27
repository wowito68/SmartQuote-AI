import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import get_settings

SQLITE_DB_PATH = Path("/tmp/smartquote_iteration7_test.db")
DEFAULT_TEST_DATABASE_URL = f"sqlite+pysqlite:///{SQLITE_DB_PATH}"
TEST_DATABASE_URL = os.environ.get("SMARTQUOTE_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
USING_SQLITE = TEST_DATABASE_URL.startswith("sqlite")

os.environ.setdefault("SMARTQUOTE_DATABASE_URL", TEST_DATABASE_URL)
os.environ["SMARTQUOTE_ENVIRONMENT"] = "test"
os.environ.setdefault("SMARTQUOTE_STORAGE_ROOT", "/tmp/smartquote_iteration7_storage")
os.environ.setdefault("SMARTQUOTE_CELERY_BROKER_URL", "memory://")
os.environ.setdefault("SMARTQUOTE_CELERY_RESULT_BACKEND", "cache+memory://")
os.environ.setdefault("SMARTQUOTE_CELERY_TASK_ALWAYS_EAGER", "true")
get_settings.cache_clear()


@pytest.fixture(scope="session")
def database_url() -> str:
    return TEST_DATABASE_URL


@pytest.fixture(scope="session")
def alembic_config(database_url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    return config


@pytest.fixture(scope="session", autouse=True)
def migrated_database(alembic_config: Config) -> Generator[None]:
    if USING_SQLITE:
        SQLITE_DB_PATH.unlink(missing_ok=True)
    command.upgrade(alembic_config, "head")
    yield
    command.downgrade(alembic_config, "base")
    if USING_SQLITE:
        SQLITE_DB_PATH.unlink(missing_ok=True)


@pytest.fixture()
def db_engine(database_url: str, migrated_database: None) -> Generator[Engine]:
    engine_options = (
        {"connect_args": {"check_same_thread": False}} if USING_SQLITE else {"pool_pre_ping": True}
    )
    engine = create_engine(database_url, **engine_options)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(db_engine: Engine) -> Generator[Session]:
    session_factory = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    with session_factory() as session:
        yield session
        session.rollback()


@pytest.fixture(autouse=True)
def clean_database_after_test(db_engine: Engine) -> Generator[None]:
    yield
    with db_engine.begin() as connection:
        connection.execute(text("DELETE FROM supplier_merge_suggestions"))
        connection.execute(text("DELETE FROM product_supplier_matches"))
        connection.execute(text("DELETE FROM tender_suppliers"))
        connection.execute(text("DELETE FROM supplier_contacts"))
        connection.execute(text("DELETE FROM supplier_sources"))
        connection.execute(text("DELETE FROM suppliers"))
        connection.execute(text("DELETE FROM supplier_discovery_runs"))
        connection.execute(text("DELETE FROM catalog_product_revisions"))
        connection.execute(text("DELETE FROM evidence_references"))
        connection.execute(text("DELETE FROM extracted_evidence"))
        connection.execute(text("DELETE FROM catalog_products"))
        connection.execute(text("DELETE FROM catalog_snapshots"))
        connection.execute(text("DELETE FROM ai_extraction_runs"))
        connection.execute(text("DELETE FROM document_qualities"))
        connection.execute(text("DELETE FROM document_pages"))
        connection.execute(text("DELETE FROM extraction_runs"))
        connection.execute(text("DELETE FROM audit_events"))
        connection.execute(text("DELETE FROM tender_documents"))
        connection.execute(text("DELETE FROM tenders"))
        connection.execute(
            text("DELETE FROM users WHERE id != '00000000000000000000000000000001'")
        )
