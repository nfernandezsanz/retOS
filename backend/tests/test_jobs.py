from retos.jobs.tasks import ping


def test_ping_task_records_progress() -> None:
    assert ping.run() == "pong"
