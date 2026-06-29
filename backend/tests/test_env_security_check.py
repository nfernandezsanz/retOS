from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_env_security() -> ModuleType:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "check_env_security.py"
    spec = importlib.util.spec_from_file_location("check_env_security", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load env security gate from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_env(path: Path, lines: list[str]) -> Path:
    env_path = path / ".env"
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return env_path


def test_env_security_warns_when_env_file_is_missing(tmp_path: Path) -> None:
    gate = load_env_security()

    checks = gate.validate_env_file(tmp_path / ".env", allow_missing=True)

    assert checks == [gate.EnvSecurityCheck("file", "WARN", f"{tmp_path / '.env'} does not exist")]


def test_env_security_fails_when_required_env_file_is_missing(tmp_path: Path) -> None:
    gate = load_env_security()

    checks = gate.validate_env_file(tmp_path / ".env", allow_missing=False)

    assert checks[0].status == "FAIL"
    assert checks[0].name == "file"


def test_env_security_accepts_safe_development_defaults(tmp_path: Path) -> None:
    gate = load_env_security()
    env_path = write_env(
        tmp_path,
        [
            "RETOS_ENV=development",
            "RETOS_JWT_SECRET=development-secret-value-that-is-long-enough",
            "RETOS_PROVIDER=local",
            "RETOS_ALLOW_PAID_LLM=false",
            "RETOS_OLLAMA_MODEL=gemma4",
        ],
    )

    checks = gate.validate_env_file(env_path)

    assert not [check for check in checks if check.status == "FAIL"]
    assert any(check.name == "RETOS_OLLAMA_MODEL" and check.status == "OK" for check in checks)


def test_env_security_fails_unsafe_production_values(tmp_path: Path) -> None:
    gate = load_env_security()
    env_path = write_env(
        tmp_path,
        [
            "RETOS_ENV=production",
            "RETOS_JWT_SECRET=change-this-development-secret-at-least-32-chars",
            "RETOS_BOOTSTRAP_ADMIN_PASSWORD=retos-dev-admin-change-me",
            "RETOS_ALLOWED_ORIGINS=*",
            "RETOS_PROVIDER=local",
            "RETOS_ALLOW_PAID_LLM=false",
            "RETOS_OLLAMA_MODEL=gemma4",
        ],
    )

    checks = gate.validate_env_file(env_path)

    failures = {check.name for check in checks if check.status == "FAIL"}
    assert "RETOS_JWT_SECRET.production" in failures
    assert "RETOS_BOOTSTRAP_ADMIN_PASSWORD.production" in failures
    assert "RETOS_ALLOWED_ORIGINS" in failures


def test_env_security_requires_paid_provider_opt_in(tmp_path: Path) -> None:
    gate = load_env_security()
    env_path = write_env(
        tmp_path,
        [
            "RETOS_ENV=development",
            "RETOS_JWT_SECRET=development-secret-value-that-is-long-enough",
            "RETOS_PROVIDER=openai",
            "RETOS_ALLOW_PAID_LLM=false",
        ],
    )

    checks = gate.validate_env_file(env_path)

    failure = next(check for check in checks if check.name == "paid provider")
    assert failure.status == "FAIL"


def test_env_security_renders_summary() -> None:
    gate = load_env_security()

    rendered = gate.render_checks(
        [
            gate.EnvSecurityCheck("RETOS_ENV", "OK", "development"),
            gate.EnvSecurityCheck("RETOS_ALLOW_PAID_LLM", "WARN", "enabled"),
            gate.EnvSecurityCheck("RETOS_JWT_SECRET", "FAIL", "short"),
        ]
    )

    assert "RetOS environment security" in rendered
    assert "[OK  ] RETOS_ENV" in rendered
    assert "Summary: 1 failure(s), 1 warning(s)" in rendered
