from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_local_access() -> ModuleType:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "local_access.py"
    spec = importlib.util.spec_from_file_location("local_access", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load local access script from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_local_access_prints_default_development_credentials(tmp_path: Path) -> None:
    access = load_local_access()
    (tmp_path / ".env.example").write_text(
        "\n".join(
            (
                "RETOS_BOOTSTRAP_ADMIN_EMAIL=admin@retos.dev",
                "RETOS_BOOTSTRAP_ADMIN_PASSWORD=retos-dev-admin-change-me",
                "",
            )
        ),
        encoding="utf-8",
    )

    output = access.render_local_access(tmp_path)

    assert "Config source: .env.example" in output
    assert "Console:   http://localhost:8080" in output
    assert "Email:    admin@retos.dev" in output
    assert "Password: retos-dev-admin-change-me" in output


def test_local_access_does_not_print_custom_local_password(tmp_path: Path) -> None:
    access = load_local_access()
    (tmp_path / ".env.example").write_text(
        "RETOS_BOOTSTRAP_ADMIN_PASSWORD=retos-dev-admin-change-me\n",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        "\n".join(
            (
                "RETOS_BOOTSTRAP_ADMIN_EMAIL=owner@example.test",
                "RETOS_BOOTSTRAP_ADMIN_PASSWORD=custom-secret-password",
                "",
            )
        ),
        encoding="utf-8",
    )

    output = access.render_local_access(tmp_path)

    assert "Config source: .env" in output
    assert "Email:    owner@example.test" in output
    assert "Password: configured in .env; not printed" in output
    assert "custom-secret-password" not in output


def test_local_access_does_not_print_production_placeholder_password(
    tmp_path: Path,
) -> None:
    access = load_local_access()
    (tmp_path / ".env").write_text(
        "\n".join(
            (
                "RETOS_ENV=production",
                "RETOS_BOOTSTRAP_ADMIN_EMAIL=owner@example.test",
                "RETOS_BOOTSTRAP_ADMIN_PASSWORD=retos-dev-admin-change-me",
                "",
            )
        ),
        encoding="utf-8",
    )

    output = access.render_local_access(tmp_path)

    assert "Email:    owner@example.test" in output
    assert "Password: development placeholder configured for production; not printed" in output
    assert "Password: retos-dev-admin-change-me" not in output


def test_local_access_defaults_missing_admin_values(tmp_path: Path) -> None:
    access = load_local_access()
    (tmp_path / ".env.example").write_text("RETOS_PROVIDER=local\n", encoding="utf-8")

    output = access.render_local_access(tmp_path)

    assert "Email:    admin@retos.dev" in output
    assert "Password: retos-dev-admin-change-me" in output
