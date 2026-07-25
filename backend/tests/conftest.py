import os
from collections.abc import Generator

import pytest
from alembic import command
from alembic.config import Config
from app.config.settings import get_settings
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

TEST_DATABASE_URL = "postgresql+psycopg://smartquote:smartquote@localhost:5433/smartquote"

os.environ.setdefault("SMARTQUOTE_DATABASE_URL", TEST_DATABASE_URL)
get_settings.cache_clear()


@pytest.fixture(scope="session")
def database_url() -> str:
    return os.environ["SMARTQUOTE_DATABASE_URL"]


@pytest.fixture(scope="session")
def alembic_config(database_url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    return config


@pytest.fixture(scope="session")
def migrated_database(alembic_config: Config) -> Generator[None]:
    command.upgrade(alembic_config, "head")
    yield


@pytest.fixture()
def db_engine(database_url: str, migrated_database: None) -> Generator[Engine]:
    engine = create_engine(database_url, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(db_engine: Engine) -> Generator[Session]:
    session_factory = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    with session_factory() as session:
        yield session
        session.rollback()
        session.execute(text("DELETE FROM tender_documents"))
        session.execute(text("DELETE FROM tenders"))
        session.execute(text("DELETE FROM users"))
        session.commit()
