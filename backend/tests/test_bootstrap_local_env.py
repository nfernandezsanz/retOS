from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_bootstrap_local_env() -> ModuleType:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "bootstrap_local_env.py"
    spec = importlib.util.spec_from_file_location("bootstrap_local_env", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load bootstrap script from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_bootstrap_env_creates_local_env_from_example(tmp_path: Path) -> None:
    bootstrap = load_bootstrap_local_env()
    (tmp_path / ".env.example").write_text("RETOS_PROVIDER=local\n", encoding="utf-8")

    message = bootstrap.bootstrap_env(tmp_path)

    assert "Created local environment" in message
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "RETOS_PROVIDER=local\n"


def test_bootstrap_env_does_not_overwrite_existing_local_env(tmp_path: Path) -> None:
    bootstrap = load_bootstrap_local_env()
    (tmp_path / ".env.example").write_text("RETOS_PROVIDER=local\n", encoding="utf-8")
    (tmp_path / ".env").write_text("RETOS_PROVIDER=openai\n", encoding="utf-8")

    message = bootstrap.bootstrap_env(tmp_path)

    assert "already exists" in message
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "RETOS_PROVIDER=openai\n"


def test_bootstrap_env_fails_when_example_is_missing(tmp_path: Path) -> None:
    bootstrap = load_bootstrap_local_env()

    try:
        bootstrap.bootstrap_env(tmp_path)
    except SystemExit as exc:
        assert "Missing" in str(exc)
        assert ".env.example" in str(exc)
    else:
        raise AssertionError("Expected missing .env.example to fail")
