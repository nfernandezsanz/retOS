#!/usr/bin/env python3
from __future__ import annotations

import argparse
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


@dataclass(frozen=True)
class EnvSecurityCheck:
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


def ok(name: str, detail: str) -> EnvSecurityCheck:
    return EnvSecurityCheck(name=name, status="OK", detail=detail)


def warn(name: str, detail: str) -> EnvSecurityCheck:
    return EnvSecurityCheck(name=name, status="WARN", detail=detail)


def fail(name: str, detail: str) -> EnvSecurityCheck:
    return EnvSecurityCheck(name=name, status="FAIL", detail=detail)


def validate_env_file(
    path: Path,
    *,
    allow_missing: bool = True,
) -> list[EnvSecurityCheck]:
    if not path.is_file():
        missing = f"{path} does not exist"
        return [warn("file", missing)] if allow_missing else [fail("file", missing)]
    return validate_env(parse_env(path))


def validate_env(env: dict[str, str]) -> list[EnvSecurityCheck]:
    checks: list[EnvSecurityCheck] = []
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
        ok("RETOS_ENV", runtime_env)
        if runtime_env in {"development", "test", "production"}
        else fail("RETOS_ENV", f"unknown environment: {runtime_env!r}")
    )
    checks.append(
        ok("RETOS_JWT_SECRET", "present and long enough")
        if len(jwt_secret) >= 32
        else fail("RETOS_JWT_SECRET", "must contain at least 32 characters")
    )
    if (
        runtime_env == "production"
        and jwt_secret == EXPECTED_DEVELOPMENT_JWT_PLACEHOLDER
    ):
        checks.append(
            fail(
                "RETOS_JWT_SECRET.production",
                "development placeholder is not allowed in production",
            )
        )
    if bootstrap_password:
        checks.append(
            ok("RETOS_BOOTSTRAP_ADMIN_PASSWORD", "present and long enough")
            if len(bootstrap_password) >= MIN_ADMIN_PASSWORD_LENGTH
            else fail(
                "RETOS_BOOTSTRAP_ADMIN_PASSWORD",
                f"must contain at least {MIN_ADMIN_PASSWORD_LENGTH} characters",
            )
        )
        if (
            runtime_env == "production"
            and bootstrap_password == EXPECTED_DEVELOPMENT_ADMIN_PASSWORD
        ):
            checks.append(
                fail(
                    "RETOS_BOOTSTRAP_ADMIN_PASSWORD.production",
                    "development placeholder is not allowed in production",
                )
            )
    checks.append(
        ok("RETOS_PROVIDER", provider)
        if provider in KNOWN_PROVIDER_PROFILES
        else fail("RETOS_PROVIDER", f"unknown provider profile: {provider!r}")
    )
    if allow_paid == "true":
        checks.append(
            warn(
                "RETOS_ALLOW_PAID_LLM",
                "paid providers are enabled; tests still mock providers by default",
            )
        )
    elif allow_paid == "false":
        checks.append(ok("RETOS_ALLOW_PAID_LLM", "false"))
    else:
        checks.append(fail("RETOS_ALLOW_PAID_LLM", "must be 'true' or 'false'"))
    if provider in PAID_PROVIDER_PROFILES and allow_paid != "true":
        checks.append(
            fail(
                "paid provider",
                "paid provider profile requires RETOS_ALLOW_PAID_LLM=true",
            )
        )
    if runtime_env != "development" and "*" in allowed_origins:
        checks.append(
            fail(
                "RETOS_ALLOWED_ORIGINS",
                "wildcard CORS origins are only allowed in development",
            )
        )
    if provider == "local":
        ollama_model = env.get("RETOS_OLLAMA_MODEL", "")
        checks.append(
            ok("RETOS_OLLAMA_MODEL", ollama_model)
            if ollama_model == "gemma4"
            else warn("RETOS_OLLAMA_MODEL", "expected local default gemma4")
        )
    return checks


def render_checks(checks: list[EnvSecurityCheck]) -> str:
    width = max(len(check.name) for check in checks) if checks else 0
    lines = ["RetOS environment security"]
    for check in checks:
        lines.append(f"[{check.status:<4}] {check.name:<{width}}  {check.detail}")
    failures = sum(check.status == "FAIL" for check in checks)
    warnings = sum(check.status == "WARN" for check in checks)
    lines.append(f"Summary: {failures} failure(s), {warnings} warning(s)")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate RetOS environment security settings."
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=ROOT / ".env",
        help="Environment file to validate. Missing files warn by default.",
    )
    parser.add_argument(
        "--require-file",
        action="store_true",
        help="Fail when the environment file is missing.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as failures.",
    )
    args = parser.parse_args()
    checks = validate_env_file(args.env_file, allow_missing=not args.require_file)
    print(render_checks(checks))
    has_failures = any(check.status == "FAIL" for check in checks)
    has_warnings = any(check.status == "WARN" for check in checks)
    if has_failures or (args.strict and has_warnings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
