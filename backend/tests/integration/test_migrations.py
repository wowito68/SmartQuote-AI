from alembic.config import Config
from sqlalchemy import Engine, inspect, text


def test_migrations_create_tender_and_audit_tables(
    alembic_config: Config,
    db_engine: Engine,
    migrated_database: None,
) -> None:
    inspector = inspect(db_engine)
    expected_tables = {"users", "tenders", "tender_documents", "audit_events"}
    assert expected_tables.issubset(inspector.get_table_names())

    with db_engine.connect() as connection:
        query = text(
            "SELECT COUNT(*) FROM users "
            "WHERE email = 'system@smartquote.local'"
        )
        count = connection.execute(query)
        assert count.scalar_one() == 1
