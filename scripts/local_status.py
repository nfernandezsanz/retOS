#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]
UrlChecker = Callable[[str, float], tuple[bool, str]]


@dataclass(frozen=True)
class StatusCheck:
    name: str
    status: str
    detail: str


def default_runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed local status inspection command.
        list(command),
        text=True,
        capture_output=True,
        check=False,
    )


def default_url_checker(url: str, timeout: float) -> tuple[bool, str]:
    try:
        with urlopen(
            url, timeout=timeout
        ) as response:  # noqa: S310 - local status URLs only.
            body = response.read(2048).decode("utf-8", errors="replace")
            return (
                200 <= response.status < 400,
                f"HTTP {response.status}: {body[:120].strip()}",
            )
    except URLError as exc:
        return False, str(exc.reason)
    except OSError as exc:
        return False, str(exc)


def ok(name: str, detail: str) -> StatusCheck:
    return StatusCheck(name=name, status="OK", detail=detail)


def warn(name: str, detail: str) -> StatusCheck:
    return StatusCheck(name=name, status="WARN", detail=detail)


def fail(name: str, detail: str) -> StatusCheck:
    return StatusCheck(name=name, status="FAIL", detail=detail)


def parse_compose_services(output: str) -> list[dict[str, Any]]:
    stripped = output.strip()
    if not stripped:
        return []
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        services = []
        for line in stripped.splitlines():
            line = line.strip()
            if not line:
                continue
            services.append(json.loads(line))
        return services
    if isinstance(parsed, list):
        return [service for service in parsed if isinstance(service, dict)]
    if isinstance(parsed, dict):
        return [parsed]
    return []


def service_name(service: dict[str, Any]) -> str:
    return str(service.get("Service") or service.get("Name") or "unknown")


def service_state(service: dict[str, Any]) -> str:
    return str(service.get("State") or service.get("Status") or "unknown")


def service_succeeded(service: dict[str, Any]) -> bool:
    state = service_state(service).lower()
    status = str(service.get("Status") or "").lower()
    exit_code = service.get("ExitCode")
    if state == "running":
        return True
    if exit_code in (0, "0"):
        return True
    return "exited (0)" in status or "exit 0" in status or status == "completed"


def collect_compose_checks(runner: CommandRunner = default_runner) -> list[StatusCheck]:
    result = runner(["docker", "compose", "ps", "--all", "--format", "json"])
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "docker compose ps failed").strip()
        return [fail("docker compose", detail)]
    try:
        services = parse_compose_services(result.stdout)
    except json.JSONDecodeError as exc:
        return [fail("docker compose", f"could not parse compose JSON: {exc}")]

    required = {"api", "worker", "web", "postgres", "rabbitmq"}
    by_name = {service_name(service): service for service in services}
    checks: list[StatusCheck] = []
    for name in sorted(required):
        service = by_name.get(name)
        if service is None:
            checks.append(fail(f"service:{name}", "not present in docker compose ps"))
            continue
        state = service_state(service)
        if state.lower() == "running":
            health = str(service.get("Health") or "")
            suffix = f", health={health}" if health else ""
            checks.append(ok(f"service:{name}", f"{state}{suffix}"))
        else:
            checks.append(fail(f"service:{name}", state))
    migrate = by_name.get("migrate")
    if migrate is None:
        checks.append(warn("service:migrate", "not present in docker compose ps --all"))
    elif service_succeeded(migrate):
        state = service_state(migrate)
        status = str(migrate.get("Status") or "").strip()
        detail = f"{state}, {status}" if status else state
        checks.append(ok("service:migrate", detail))
    else:
        status = str(migrate.get("Status") or service_state(migrate)).strip()
        checks.append(fail("service:migrate", status))
    return checks


def collect_endpoint_checks(
    checker: UrlChecker = default_url_checker,
    *,
    timeout: float = 2.0,
) -> list[StatusCheck]:
    endpoints = [
        ("console", "http://localhost:8080", True),
        ("api readiness", "http://localhost:8000/readyz", True),
        ("api docs", "http://localhost:8000/docs", True),
        ("api version", "http://localhost:8000/versionz", True),
        ("rabbitmq management", "http://localhost:15672", False),
    ]
    checks: list[StatusCheck] = []
    for name, url, required in endpoints:
        available, detail = checker(url, timeout)
        if available:
            checks.append(ok(name, url))
        elif required:
            checks.append(fail(name, f"{url} unavailable: {detail}"))
        else:
            checks.append(warn(name, f"{url} unavailable: {detail}"))
    return checks


def collect_status(
    *,
    runner: CommandRunner = default_runner,
    checker: UrlChecker = default_url_checker,
    timeout: float = 2.0,
) -> list[StatusCheck]:
    return [
        *collect_compose_checks(runner),
        *collect_endpoint_checks(checker, timeout=timeout),
    ]


def render_status(checks: Sequence[StatusCheck]) -> str:
    width = max(len(check.name) for check in checks) if checks else 0
    lines = [
        "RetOS local status",
        "URLs:",
        "  Console:   http://localhost:8080",
        "  API docs:  http://localhost:8000/docs",
        "  Readiness: http://localhost:8000/readyz",
        "  RabbitMQ:  http://localhost:15672",
        "",
        "Checks:",
    ]
    for check in checks:
        lines.append(f"[{check.status:<4}] {check.name:<{width}}  {check.detail}")
    failures = sum(check.status == "FAIL" for check in checks)
    warnings = sum(check.status == "WARN" for check in checks)
    lines.append(f"Summary: {failures} failure(s), {warnings} warning(s)")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Show local RetOS Docker stack status."
    )
    parser.add_argument(
        "--timeout", type=float, default=2.0, help="Endpoint timeout in seconds."
    )
    parser.add_argument(
        "--strict", action="store_true", help="Treat warnings as failures."
    )
    args = parser.parse_args()

    checks = collect_status(timeout=args.timeout)
    print(render_status(checks))
    has_failures = any(check.status == "FAIL" for check in checks)
    has_warnings = any(check.status == "WARN" for check in checks)
    if has_failures or (args.strict and has_warnings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
