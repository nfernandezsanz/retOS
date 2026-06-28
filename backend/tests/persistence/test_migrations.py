from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from retos.persistence.models import Base

BACKEND_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_TABLES = {
    "admin_user_domain_grants",
    "admin_users",
    "artifacts",
    "document_versions",
    "documents",
    "domains",
    "jobs",
    "journal_events",
    "progress_events",
    "segments",
    "sources",
}


def alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_orm_metadata_declares_expected_persistence_tables() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_initial_migration_creates_and_drops_catalog_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "retos.db"
    async_database_url = f"sqlite+aiosqlite:///{db_path}"
    sync_database_url = f"sqlite:///{db_path}"
    config = alembic_config(async_database_url)

    command.upgrade(config, "head")

    engine = create_engine(sync_database_url)
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())

        assert EXPECTED_TABLES.issubset(tables)
        assert "alembic_version" in tables
        assert {item["name"] for item in inspector.get_unique_constraints("sources")} == {
            "uq_sources_domain_uri"
        }
        assert {item["name"] for item in inspector.get_unique_constraints("document_versions")} == {
            "uq_document_versions_document_version"
        }
        assert {item["name"] for item in inspector.get_indexes("jobs")} >= {
            "ix_jobs_kind",
            "ix_jobs_status",
        }
        admin_columns = {item["name"] for item in inspector.get_columns("admin_users")}
        assert "roles" in admin_columns
        assert {
            item["name"] for item in inspector.get_unique_constraints("admin_user_domain_grants")
        } == {"uq_admin_user_domain_grants_user_domain"}
    finally:
        engine.dispose()

    command.downgrade(config, "base")

    engine = create_engine(sync_database_url)
    try:
        remaining_tables = set(inspect(engine).get_table_names())
        assert remaining_tables == {"alembic_version"}
    finally:
        engine.dispose()
