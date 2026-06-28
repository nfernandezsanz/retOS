import pytest
from pydantic import SecretStr
from sqlalchemy.exc import IntegrityError

from retos.core.config import Settings
from retos.persistence import bootstrap as bootstrap_module
from retos.persistence import unit_of_work as uow_module
from retos.persistence.bootstrap import bootstrap_admin_user
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
