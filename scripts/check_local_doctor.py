#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from check_env_security import (  # noqa: E402
    EXPECTED_DEVELOPMENT_JWT_PLACEHOLDER,
    parse_env,
    validate_env_file,
)

CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str
    detail: str


def default_runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - commands are fixed local prerequisite checks.
        list(command),
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def ok(name: str, detail: str) -> DoctorCheck:
    return DoctorCheck(name=name, status="OK", detail=detail)


def warn(name: str, detail: str) -> DoctorCheck:
    return DoctorCheck(name=name, status="WARN", detail=detail)


def fail(name: str, detail: str) -> DoctorCheck:
    return DoctorCheck(name=name, status="FAIL", detail=detail)


def command_check(
    name: str,
    command: Sequence[str],
    *,
    runner: CommandRunner,
    required_binary: str | None = None,
) -> DoctorCheck:
    binary = required_binary or command[0]
    if shutil.which(binary) is None:
        return fail(name, f"{binary} is not available on PATH")
    result = runner(command)
    output = (result.stdout or result.stderr).strip().splitlines()
    detail = output[0] if output else f"{' '.join(command)} exited {result.returncode}"
    if result.returncode == 0:
        return ok(name, detail)
    return fail(name, detail)


def file_checks(root: Path) -> list[DoctorCheck]:
    required_files = (
        ".env.example",
        "docker-compose.yml",
        "backend/requirements-dev.txt",
        "backend/pyproject.toml",
        "frontend/package.json",
        "frontend/package-lock.json",
        "Makefile",
    )
    checks: list[DoctorCheck] = []
    for relative in required_files:
        path = root / relative
        checks.append(
            ok(f"file:{relative}", "present")
            if path.is_file()
            else fail(f"file:{relative}", "missing")
        )
    env_path = root / ".env"
    checks.append(
        ok("local .env", ".env exists")
        if env_path.is_file()
        else warn(
            "local .env", "missing; run cp .env.example .env before docker compose up"
        )
    )
    return checks


def local_env_checks(root: Path) -> list[DoctorCheck]:
    env_path = root / ".env"
    if not env_path.is_file():
        return []
    return [
        DoctorCheck(
            name=f"local env:{check.name}",
            status=check.status,
            detail=(
                "paid providers are enabled in local .env; tests still mock providers"
                if check.name == "RETOS_ALLOW_PAID_LLM" and check.status == "WARN"
                else check.detail
            ),
        )
        for check in validate_env_file(env_path, allow_missing=True)
    ]


def env_safety_checks(root: Path) -> list[DoctorCheck]:
    env = parse_env(root / ".env.example")
    expected = {
        "RETOS_ALLOW_PAID_LLM": "false",
        "RETOS_PROVIDER": "local",
        "RETOS_AGENT_RUNTIME": "deterministic",
        "RETOS_OLLAMA_MODEL": "gemma4",
        "RETOS_BOOTSTRAP_ADMIN_PASSWORD": "retos-dev-admin-change-me",
    }
    checks: list[DoctorCheck] = []
    for key, value in expected.items():
        actual = env.get(key)
        checks.append(
            ok(f"env:{key}", actual)
            if actual == value
            else fail(f"env:{key}", f"expected {value!r}, got {actual!r}")
        )
    jwt_secret = env.get("RETOS_JWT_SECRET", "")
    checks.append(
        ok(
            "env:RETOS_JWT_SECRET",
            "development placeholder is explicit and long enough",
        )
        if jwt_secret == EXPECTED_DEVELOPMENT_JWT_PLACEHOLDER
        else fail("env:RETOS_JWT_SECRET", "development placeholder changed or missing")
    )
    return checks


def collect_checks(
    root: Path = ROOT,
    *,
    runner: CommandRunner = default_runner,
) -> list[DoctorCheck]:
    checks = [*file_checks(root), *env_safety_checks(root), *local_env_checks(root)]
    checks.append(
        ok(
            "python",
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        )
        if sys.version_info >= (3, 14)
        else fail("python", "Python 3.14 or newer is required")
    )
    checks.extend(
        [
            command_check("node", ["node", "--version"], runner=runner),
            command_check("npm", ["npm", "--version"], runner=runner),
            command_check(
                "docker compose",
                ["docker", "compose", "version"],
                runner=runner,
                required_binary="docker",
            ),
            command_check(
                "compose config",
                ["docker", "compose", "--env-file", ".env.example", "config"],
                runner=runner,
                required_binary="docker",
            ),
            command_check(
                "topology guard",
                ["scripts/check_docker_topology.sh"],
                runner=runner,
                required_binary="scripts/check_docker_topology.sh",
            ),
            command_check(
                "audit export verifier",
                [sys.executable, "scripts/check_audit_export.py", "--self-test"],
                runner=runner,
                required_binary=sys.executable,
            ),
        ]
    )
    return checks


def render_checks(checks: Sequence[DoctorCheck]) -> str:
    width = max(len(check.name) for check in checks) if checks else 0
    lines = ["RetOS local doctor"]
    for check in checks:
        lines.append(f"[{check.status:<4}] {check.name:<{width}}  {check.detail}")
    failures = sum(check.status == "FAIL" for check in checks)
    warnings = sum(check.status == "WARN" for check in checks)
    lines.append(f"Summary: {failures} failure(s), {warnings} warning(s)")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check local RetOS development prerequisites."
    )
    parser.add_argument(
        "--strict", action="store_true", help="Treat warnings as failures."
    )
    args = parser.parse_args()
    checks = collect_checks()
    print(render_checks(checks))
    has_failures = any(check.status == "FAIL" for check in checks)
    has_warnings = any(check.status == "WARN" for check in checks)
    if has_failures or (args.strict and has_warnings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
