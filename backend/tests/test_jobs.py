from types import SimpleNamespace

import pytest

from retos.jobs import tasks
from retos.jobs.tasks import ping


def test_ping_task_records_progress() -> None:
    assert ping.run() == "pong"


@pytest.mark.asyncio
async def test_text_ingestion_task_disposes_engine_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, object]] = []
    result = SimpleNamespace(document=SimpleNamespace(id="document-1"))

    monkeypatch.setattr(tasks, "get_settings", lambda: SimpleNamespace(database_url="sqlite://"))
    monkeypatch.setattr(
        tasks, "create_engine", lambda url: calls.append(("engine", url)) or "engine"
    )
    monkeypatch.setattr(
        tasks,
        "create_session_factory",
        lambda engine: calls.append(("factory", engine)) or "factory",
    )
    monkeypatch.setattr(
        tasks,
        "SQLAlchemyUnitOfWork",
        lambda factory: calls.append(("uow", factory)) or SimpleNamespace(),
    )

    async def fake_run_text_ingestion(**kwargs: object) -> object:
        calls.append(("run", kwargs["job_id"]))
        return result

    async def fake_dispose_engine(engine: object) -> None:
        calls.append(("dispose", engine))

    monkeypatch.setattr(tasks, "run_text_ingestion", fake_run_text_ingestion)
    monkeypatch.setattr(tasks, "dispose_engine", fake_dispose_engine)

    document_id = await tasks._run_text_ingestion_task("job-1")

    assert document_id == "document-1"
    assert ("run", "job-1") in calls
    assert calls[-1] == ("dispose", "engine")


@pytest.mark.asyncio
async def test_text_ingestion_task_marks_failure_and_disposes_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(tasks, "get_settings", lambda: SimpleNamespace(database_url="sqlite://"))
    monkeypatch.setattr(tasks, "create_engine", lambda url: "engine")
    monkeypatch.setattr(tasks, "create_session_factory", lambda engine: "factory")
    monkeypatch.setattr(tasks, "SQLAlchemyUnitOfWork", lambda factory: SimpleNamespace())

    async def fake_run_text_ingestion(**_: object) -> object:
        raise RuntimeError("broken ingestion")

    async def fake_fail_text_ingestion_job(**kwargs: object) -> None:
        calls.append(("fail", kwargs["error"]))

    async def fake_dispose_engine(engine: object) -> None:
        calls.append(("dispose", engine))

    monkeypatch.setattr(tasks, "run_text_ingestion", fake_run_text_ingestion)
    monkeypatch.setattr(tasks, "fail_text_ingestion_job", fake_fail_text_ingestion_job)
    monkeypatch.setattr(tasks, "dispose_engine", fake_dispose_engine)

    with pytest.raises(RuntimeError, match="broken ingestion"):
        await tasks._run_text_ingestion_task("job-1")

    assert ("fail", "broken ingestion") in calls
    assert calls[-1] == ("dispose", "engine")


@pytest.mark.asyncio
async def test_rebuild_domain_index_task_disposes_engine_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, object]] = []
    result = SimpleNamespace(segment_count=3)

    monkeypatch.setattr(
        tasks,
        "get_settings",
        lambda: SimpleNamespace(database_url="sqlite://", index_root="retos-test-index"),
    )
    monkeypatch.setattr(tasks, "create_engine", lambda url: "engine")
    monkeypatch.setattr(tasks, "create_session_factory", lambda engine: "factory")
    monkeypatch.setattr(tasks, "SQLAlchemyUnitOfWork", lambda factory: SimpleNamespace())
    monkeypatch.setattr(
        tasks, "TantivySearchIndex", lambda root: calls.append(("index", root)) or "index"
    )

    async def fake_rebuild_domain_index(**kwargs: object) -> object:
        calls.append(("rebuild", kwargs["job_id"]))
        return result

    async def fake_dispose_engine(engine: object) -> None:
        calls.append(("dispose", engine))

    monkeypatch.setattr(tasks, "rebuild_domain_index", fake_rebuild_domain_index)
    monkeypatch.setattr(tasks, "dispose_engine", fake_dispose_engine)

    segment_count = await tasks._rebuild_domain_index_task("job-idx")

    assert segment_count == 3
    assert ("index", "retos-test-index") in calls
    assert ("rebuild", "job-idx") in calls
    assert calls[-1] == ("dispose", "engine")


@pytest.mark.asyncio
async def test_rebuild_domain_index_task_marks_failure_and_disposes_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(
        tasks,
        "get_settings",
        lambda: SimpleNamespace(database_url="sqlite://", index_root="retos-test-index"),
    )
    monkeypatch.setattr(tasks, "create_engine", lambda url: "engine")
    monkeypatch.setattr(tasks, "create_session_factory", lambda engine: "factory")
    monkeypatch.setattr(tasks, "SQLAlchemyUnitOfWork", lambda factory: SimpleNamespace())
    monkeypatch.setattr(tasks, "TantivySearchIndex", lambda root: "index")

    async def fake_rebuild_domain_index(**_: object) -> object:
        raise RuntimeError("broken index")

    async def fake_fail_index_job(**kwargs: object) -> None:
        calls.append(("fail", kwargs["error"]))

    async def fake_dispose_engine(engine: object) -> None:
        calls.append(("dispose", engine))

    monkeypatch.setattr(tasks, "rebuild_domain_index", fake_rebuild_domain_index)
    monkeypatch.setattr(tasks, "fail_index_job", fake_fail_index_job)
    monkeypatch.setattr(tasks, "dispose_engine", fake_dispose_engine)

    with pytest.raises(RuntimeError, match="broken index"):
        await tasks._rebuild_domain_index_task("job-idx")

    assert ("fail", "broken index") in calls
    assert calls[-1] == ("dispose", "engine")
