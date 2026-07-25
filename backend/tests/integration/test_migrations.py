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

    document_columns = {
        column["name"] for column in inspector.get_columns("tender_documents")
    }
    assert "deleted_at" in document_columns
    check_constraints = inspector.get_check_constraints("tender_documents")
    status_checks = [
        constraint["sqltext"]
        for constraint in check_constraints
        if "processing_status" in (constraint.get("sqltext") or "")
    ]
    assert len(status_checks) == 1
    assert all(state in status_checks[0] for state in ("uploaded", "deleted", "rejected"))
    assert "processed" not in status_checks[0]

    with db_engine.connect() as connection:
        query = text(
            "SELECT COUNT(*) FROM users "
            "WHERE email = 'system@smartquote.local'"
        )
        count = connection.execute(query)
        assert count.scalar_one() == 1
