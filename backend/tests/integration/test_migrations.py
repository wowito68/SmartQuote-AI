from alembic.config import Config
from sqlalchemy import Engine, inspect


def test_initial_migration_creates_core_tables(
    alembic_config: Config,
    db_engine: Engine,
    migrated_database: None,
) -> None:
    inspector = inspect(db_engine)

    assert {"users", "tenders", "tender_documents"}.issubset(inspector.get_table_names())

    tender_columns = {column["name"] for column in inspector.get_columns("tenders")}
    assert {"id", "title", "status", "created_by_user_id", "deleted_at"}.issubset(
        tender_columns
    )

