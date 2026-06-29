from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy.exc import IntegrityError

from retos.core.config import Settings
from retos.persistence import bootstrap as bootstrap_module
from retos.persistence import unit_of_work as uow_module
from retos.persistence.bootstrap import bootstrap_admin_user
from retos.persistence.database import (
    create_engine,
    create_schema,
    create_session_factory,
    dispose_engine,
)
from retos.persistence.unit_of_work import SQLAlchemyUnitOfWork


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def close(self) -> None:
        self.closes += 1


@pytest.mark.asyncio
async def test_unit_of_work_commit_and_rollback_require_entered_session() -> None:
    uow = SQLAlchemyUnitOfWork(lambda: FakeSession())  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="Unit of work has not been entered"):
        await uow.commit()
    with pytest.raises(RuntimeError, match="Unit of work has not been entered"):
        await uow.rollback()


@pytest.mark.asyncio
async def test_unit_of_work_exit_before_enter_is_noop() -> None:
    uow = SQLAlchemyUnitOfWork(lambda: FakeSession())  # type: ignore[arg-type]

    await uow.__aexit__(None, None, None)

    assert uow.session is None


@pytest.mark.asyncio
async def test_unit_of_work_closes_session_and_rolls_back_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    monkeypatch.setattr(uow_module, "AdminUserRepository", lambda _: object())
    monkeypatch.setattr(uow_module, "DomainRepository", lambda _: object())
    monkeypatch.setattr(uow_module, "SourceRepository", lambda _: object())
    monkeypatch.setattr(uow_module, "DocumentRepository", lambda _: object())
    monkeypatch.setattr(uow_module, "JobRepository", lambda _: object())
    monkeypatch.setattr(uow_module, "JournalRepository", lambda _: object())
    monkeypatch.setattr(uow_module, "ProgressEventRepository", lambda _: object())

    uow = SQLAlchemyUnitOfWork(lambda: session)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="boom"):
        async with uow:
            raise ValueError("boom")

    assert session.rollbacks == 1
    assert session.closes == 1


@pytest.mark.asyncio
async def test_unit_of_work_commit_and_explicit_rollback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    monkeypatch.setattr(uow_module, "AdminUserRepository", lambda _: object())
    monkeypatch.setattr(uow_module, "DomainRepository", lambda _: object())
    monkeypatch.setattr(uow_module, "SourceRepository", lambda _: object())
    monkeypatch.setattr(uow_module, "DocumentRepository", lambda _: object())
    monkeypatch.setattr(uow_module, "JobRepository", lambda _: object())
    monkeypatch.setattr(uow_module, "JournalRepository", lambda _: object())
    monkeypatch.setattr(uow_module, "ProgressEventRepository", lambda _: object())

    async with SQLAlchemyUnitOfWork(lambda: session) as uow:  # type: ignore[arg-type]
        await uow.commit()
        await uow.rollback()

    assert session.commits == 1
    assert session.rollbacks == 1
    assert session.closes == 1


@pytest.mark.asyncio
async def test_domain_repository_updates_details_through_unit_of_work(
    tmp_path: Path,
) -> None:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'domain-update.db'}")
    await create_schema(engine)
    session_factory = create_session_factory(engine)

    try:
        async with SQLAlchemyUnitOfWork(session_factory) as uow:
            domain = await uow.domains.add(
                slug="policy",
                name="Policy",
                description="Initial boundary",
            )
            await uow.commit()

        async with SQLAlchemyUnitOfWork(session_factory) as uow:
            updated = await uow.domains.update_details(
                domain_id=domain.id,
                name="Policy Review",
                description="Updated boundary",
            )
            await uow.commit()

        async with SQLAlchemyUnitOfWork(session_factory) as uow:
            fetched = await uow.domains.get(domain.id)

        assert updated is not None
        assert updated.slug == "policy"
        assert updated.name == "Policy Review"
        assert updated.description == "Updated boundary"
        assert fetched is not None
        assert fetched.name == "Policy Review"
        assert fetched.description == "Updated boundary"
    finally:
        await dispose_engine(engine)


@pytest.mark.asyncio
async def test_domain_repository_update_details_returns_none_for_missing_domain(
    tmp_path: Path,
) -> None:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'missing-domain-update.db'}")
    await create_schema(engine)
    session_factory = create_session_factory(engine)

    try:
        async with SQLAlchemyUnitOfWork(session_factory) as uow:
            result = await uow.domains.update_details(
                domain_id="missing-domain",
                name="Missing",
                description=None,
            )

        assert result is None
    finally:
        await dispose_engine(engine)


@pytest.mark.asyncio
async def test_source_repository_updates_details_through_unit_of_work(
    tmp_path: Path,
) -> None:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'source-update.db'}")
    await create_schema(engine)
    session_factory = create_session_factory(engine)

    try:
        async with SQLAlchemyUnitOfWork(session_factory) as uow:
            domain = await uow.domains.add(
                slug="source-domain",
                name="Source Domain",
                description=None,
            )
            source = await uow.sources.add(
                domain_id=domain.id,
                kind="upload",
                name="Upload Source",
                uri="upload://source",
            )
            await uow.commit()

        async with SQLAlchemyUnitOfWork(session_factory) as uow:
            updated = await uow.sources.update_details(
                source_id=source.id,
                kind="mount",
                name="Mounted Source",
                uri="file:///source",
            )
            await uow.commit()

        async with SQLAlchemyUnitOfWork(session_factory) as uow:
            fetched = await uow.sources.get(source.id)

        assert updated is not None
        assert updated.kind == "mount"
        assert updated.name == "Mounted Source"
        assert updated.uri == "file:///source"
        assert fetched is not None
        assert fetched.kind == "mount"
        assert fetched.name == "Mounted Source"
        assert fetched.uri == "file:///source"
    finally:
        await dispose_engine(engine)


@pytest.mark.asyncio
async def test_source_repository_update_details_returns_none_for_missing_source(
    tmp_path: Path,
) -> None:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'missing-source-update.db'}")
    await create_schema(engine)
    session_factory = create_session_factory(engine)

    try:
        async with SQLAlchemyUnitOfWork(session_factory) as uow:
            result = await uow.sources.update_details(
                source_id="missing-source",
                kind="upload",
                name="Missing",
                uri="upload://missing",
            )

        assert result is None
    finally:
        await dispose_engine(engine)


@pytest.mark.asyncio
async def test_source_repository_deletes_source_and_detaches_documents(
    tmp_path: Path,
) -> None:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'source-delete.db'}")
    await create_schema(engine)
    session_factory = create_session_factory(engine)

    try:
        async with SQLAlchemyUnitOfWork(session_factory) as uow:
            domain = await uow.domains.add(
                slug="source-delete",
                name="Source Delete",
                description=None,
            )
            source = await uow.sources.add(
                domain_id=domain.id,
                kind="upload",
                name="Upload Source",
                uri="upload://source",
            )
            document, _ = await uow.documents.add_with_initial_version(
                domain_id=domain.id,
                source_id=source.id,
                external_id="source-delete-doc",
                title="Source Delete Document",
                content_hash="source-delete-hash",
                metadata={},
                source_uri="upload://source/doc.txt",
                size_bytes=12,
            )
            await uow.commit()

        async with SQLAlchemyUnitOfWork(session_factory) as uow:
            deleted = await uow.sources.delete(source.id)
            await uow.commit()

        async with SQLAlchemyUnitOfWork(session_factory) as uow:
            missing_source = await uow.sources.get(source.id)
            fetched_document = await uow.documents.get(document.id)

        assert deleted is not None
        assert deleted.id == source.id
        assert missing_source is None
        assert fetched_document is not None
        assert fetched_document.source_id is None
    finally:
        await dispose_engine(engine)


@pytest.mark.asyncio
async def test_source_repository_delete_returns_none_for_missing_source(
    tmp_path: Path,
) -> None:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'missing-source-delete.db'}")
    await create_schema(engine)
    session_factory = create_session_factory(engine)

    try:
        async with SQLAlchemyUnitOfWork(session_factory) as uow:
            result = await uow.sources.delete("missing-source")

        assert result is None
    finally:
        await dispose_engine(engine)


class FakeAdminRepository:
    def __init__(self, *, existing: object | None, fail_add: bool = False) -> None:
        self.existing = existing
        self.fail_add = fail_add
        self.added: list[tuple[str, str]] = []

    async def get_by_email(self, email: str) -> object | None:
        return self.existing

    async def add(self, *, email: str, password_hash: str) -> None:
        if self.fail_add:
            raise IntegrityError("insert admin", {}, Exception("duplicate"))
        self.added.append((email, password_hash))


class FakeBootstrapUnitOfWork:
    def __init__(self, admin_users: FakeAdminRepository) -> None:
        self.admin_users = admin_users
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self) -> FakeBootstrapUnitOfWork:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def bootstrap_settings() -> Settings:
    return Settings(
        env="test",
        jwt_secret=SecretStr("test-secret-value-that-is-long-enough"),
        bootstrap_admin_password=SecretStr("test-admin-password"),
    )


@pytest.mark.asyncio
async def test_bootstrap_admin_user_skips_existing_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_uow = FakeBootstrapUnitOfWork(FakeAdminRepository(existing=object()))
    monkeypatch.setattr(bootstrap_module, "SQLAlchemyUnitOfWork", lambda _: fake_uow)

    await bootstrap_admin_user(settings=bootstrap_settings(), session_factory=object())  # type: ignore[arg-type]

    assert fake_uow.admin_users.added == []
    assert fake_uow.commits == 0
    assert fake_uow.rollbacks == 0


@pytest.mark.asyncio
async def test_bootstrap_admin_user_rolls_back_integrity_race(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_uow = FakeBootstrapUnitOfWork(FakeAdminRepository(existing=None))

    async def fail_commit() -> None:
        fake_uow.commits += 1
        raise IntegrityError("commit admin", {}, Exception("duplicate"))

    fake_uow.commit = fail_commit  # type: ignore[method-assign]
    monkeypatch.setattr(bootstrap_module, "SQLAlchemyUnitOfWork", lambda _: fake_uow)

    await bootstrap_admin_user(settings=bootstrap_settings(), session_factory=object())  # type: ignore[arg-type]

    assert len(fake_uow.admin_users.added) == 1
    assert fake_uow.commits == 1
    assert fake_uow.rollbacks == 1
