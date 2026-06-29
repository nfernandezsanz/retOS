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
EXPECTED_DEVELOPMENT_JWT_PLACEHOLDER = (
    "change-this-development-secret-at-least-32-chars"
)
EXPECTED_DEVELOPMENT_ADMIN_PASSWORD = "retos-dev-admin-change-me"
MIN_ADMIN_PASSWORD_LENGTH = 12
KNOWN_PROVIDER_PROFILES = {
    "fake",
    "local",
    "openai",
    "anthropic",
    "google",
    "openrouter",
    "azure",
}
PAID_PROVIDER_PROFILES = {"openai", "anthropic", "google", "openrouter", "azure"}
CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str
    detail: str


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


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

    env = parse_env(env_path)
    checks: list[DoctorCheck] = []
    runtime_env = env.get("RETOS_ENV", "development")
    jwt_secret = env.get("RETOS_JWT_SECRET", "")
    bootstrap_password = env.get("RETOS_BOOTSTRAP_ADMIN_PASSWORD")
    allow_paid = env.get("RETOS_ALLOW_PAID_LLM", "false").lower()
    provider = env.get("RETOS_PROVIDER", "local")
    allowed_origins = [
        origin.strip()
        for origin in env.get("RETOS_ALLOWED_ORIGINS", "").split(",")
        if origin.strip()
    ]

    checks.append(
        ok("local env:RETOS_ENV", runtime_env)
        if runtime_env in {"development", "test", "production"}
        else fail("local env:RETOS_ENV", f"unknown environment: {runtime_env!r}")
    )
    checks.append(
        ok("local env:RETOS_JWT_SECRET", "present and long enough")
        if len(jwt_secret) >= 32
        else fail("local env:RETOS_JWT_SECRET", "must contain at least 32 characters")
    )
    if (
        runtime_env == "production"
        and jwt_secret == EXPECTED_DEVELOPMENT_JWT_PLACEHOLDER
    ):
        checks.append(
            fail(
                "local env:RETOS_JWT_SECRET.production",
                "development placeholder is not allowed in production",
            )
        )
    if bootstrap_password:
        checks.append(
            ok("local env:RETOS_BOOTSTRAP_ADMIN_PASSWORD", "present and long enough")
            if len(bootstrap_password) >= MIN_ADMIN_PASSWORD_LENGTH
            else fail(
                "local env:RETOS_BOOTSTRAP_ADMIN_PASSWORD",
                f"must contain at least {MIN_ADMIN_PASSWORD_LENGTH} characters",
            )
        )
        if (
            runtime_env == "production"
            and bootstrap_password == EXPECTED_DEVELOPMENT_ADMIN_PASSWORD
        ):
            checks.append(
                fail(
                    "local env:RETOS_BOOTSTRAP_ADMIN_PASSWORD.production",
                    "development placeholder is not allowed in production",
                )
            )
    checks.append(
        ok("local env:RETOS_PROVIDER", provider)
        if provider in KNOWN_PROVIDER_PROFILES
        else fail("local env:RETOS_PROVIDER", f"unknown provider profile: {provider!r}")
    )
    if allow_paid == "true":
        checks.append(
            warn(
                "local env:RETOS_ALLOW_PAID_LLM",
                "paid providers are enabled in local .env; tests still mock providers",
            )
        )
    elif allow_paid == "false":
        checks.append(ok("local env:RETOS_ALLOW_PAID_LLM", "false"))
    else:
        checks.append(
            fail("local env:RETOS_ALLOW_PAID_LLM", "must be 'true' or 'false'")
        )
    if provider in PAID_PROVIDER_PROFILES and allow_paid != "true":
        checks.append(
            fail(
                "local env:paid provider",
                "paid provider profile requires RETOS_ALLOW_PAID_LLM=true",
            )
        )
    if runtime_env != "development" and "*" in allowed_origins:
        checks.append(
            fail(
                "local env:RETOS_ALLOWED_ORIGINS",
                "wildcard CORS origins are only allowed in development",
            )
        )
    if provider == "local":
        ollama_model = env.get("RETOS_OLLAMA_MODEL", "")
        checks.append(
            ok("local env:RETOS_OLLAMA_MODEL", ollama_model)
            if ollama_model == "gemma4"
            else warn("local env:RETOS_OLLAMA_MODEL", "expected local default gemma4")
        )
    return checks


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
