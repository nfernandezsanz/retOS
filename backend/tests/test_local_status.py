from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType


def load_local_status() -> ModuleType:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "local_status.py"
    spec = importlib.util.spec_from_file_location("local_status", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load local status from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        ["docker", "compose", "ps"], returncode, stdout=stdout, stderr=""
    )


def test_local_status_accepts_compose_json_array() -> None:
    status = load_local_status()
    payload = json.dumps(
        [
            {"Service": "api", "State": "running", "Health": "healthy"},
            {"Service": "migrate", "State": "exited", "Status": "Exited (0) 2 minutes ago"},
            {"Service": "worker", "State": "running"},
            {"Service": "web", "State": "running"},
            {"Service": "postgres", "State": "running", "Health": "healthy"},
            {"Service": "rabbitmq", "State": "running", "Health": "healthy"},
        ]
    )

    checks = status.collect_compose_checks(lambda _command: completed(payload))

    assert {check.name: check.status for check in checks} == {
        "service:api": "OK",
        "service:migrate": "OK",
        "service:postgres": "OK",
        "service:rabbitmq": "OK",
        "service:web": "OK",
        "service:worker": "OK",
    }


def test_local_status_accepts_compose_json_lines() -> None:
    status = load_local_status()
    payload = "\n".join(
        json.dumps({"Service": service, "State": "running"})
        for service in ("api", "migrate", "worker", "web", "postgres", "rabbitmq")
    )

    checks = status.collect_compose_checks(lambda _command: completed(payload))

    assert not [check for check in checks if check.status == "FAIL"]


def test_local_status_uses_all_services_for_compose_status() -> None:
    status = load_local_status()
    commands: list[list[str]] = []
    payload = json.dumps(
        [
            {"Service": "api", "State": "running"},
            {"Service": "migrate", "State": "exited", "ExitCode": 0},
            {"Service": "worker", "State": "running"},
            {"Service": "web", "State": "running"},
            {"Service": "postgres", "State": "running"},
            {"Service": "rabbitmq", "State": "running"},
        ]
    )

    def runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        commands.append(list(command))
        return completed(payload)

    status.collect_compose_checks(runner)

    assert commands == [["docker", "compose", "ps", "--all", "--format", "json"]]


def test_local_status_fails_failed_migrations() -> None:
    status = load_local_status()
    payload = json.dumps(
        [
            {"Service": "api", "State": "running"},
            {"Service": "migrate", "State": "exited", "ExitCode": 1, "Status": "Exited (1)"},
            {"Service": "worker", "State": "running"},
            {"Service": "web", "State": "running"},
            {"Service": "postgres", "State": "running"},
            {"Service": "rabbitmq", "State": "running"},
        ]
    )

    checks = status.collect_compose_checks(lambda _command: completed(payload))

    failures = {check.name: check.detail for check in checks if check.status == "FAIL"}
    assert failures["service:migrate"] == "Exited (1)"


def test_local_status_fails_missing_required_services() -> None:
    status = load_local_status()
    payload = json.dumps([{"Service": "api", "State": "running"}])

    checks = status.collect_compose_checks(lambda _command: completed(payload))

    failures = {check.name: check.detail for check in checks if check.status == "FAIL"}
    assert failures["service:worker"] == "not present in docker compose ps"
    assert failures["service:web"] == "not present in docker compose ps"


def test_local_status_handles_required_and_optional_endpoints() -> None:
    status = load_local_status()

    def checker(url: str, _timeout: float) -> tuple[bool, str]:
        if url.endswith(":15672"):
            return False, "connection refused"
        return True, "ok"

    checks = status.collect_endpoint_checks(checker)

    by_name = {check.name: check for check in checks}
    assert by_name["console"].status == "OK"
    assert by_name["api readiness"].status == "OK"
    assert by_name["rabbitmq management"].status == "WARN"


def test_local_status_render_includes_urls_and_summary() -> None:
    status = load_local_status()

    rendered = status.render_status(
        [
            status.StatusCheck("service:api", "OK", "running"),
            status.StatusCheck("console", "FAIL", "unavailable"),
            status.StatusCheck("rabbitmq management", "WARN", "not ready"),
        ]
    )

    assert "RetOS local status" in rendered
    assert "Console:   http://localhost:8080" in rendered
    assert "[FAIL] console" in rendered
    assert "Summary: 1 failure(s), 1 warning(s)" in rendered
