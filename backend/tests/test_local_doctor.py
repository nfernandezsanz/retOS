from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType


def load_local_doctor() -> ModuleType:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "check_local_doctor.py"
    spec = importlib.util.spec_from_file_location("check_local_doctor", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load local doctor from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_minimal_repo(root: Path, *, allow_paid_llm: str = "false") -> None:
    for relative in (
        "backend",
        "frontend",
        "scripts",
    ):
        (root / relative).mkdir()
    for relative in (
        "docker-compose.yml",
        "backend/requirements-dev.txt",
        "backend/pyproject.toml",
        "frontend/package.json",
        "frontend/package-lock.json",
        "Makefile",
    ):
        (root / relative).write_text("placeholder\n", encoding="utf-8")
    (root / ".env.example").write_text(
        "\n".join(
            [
                f"RETOS_ALLOW_PAID_LLM={allow_paid_llm}",
                "RETOS_PROVIDER=local",
                "RETOS_AGENT_RUNTIME=deterministic",
                "RETOS_OLLAMA_MODEL=gemma4",
                "RETOS_BOOTSTRAP_ADMIN_PASSWORD=retos-dev-admin-change-me",
                "RETOS_JWT_SECRET=change-this-development-secret-at-least-32-chars",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    topology = root / "scripts" / "check_docker_topology.sh"
    topology.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    topology.chmod(0o755)


def successful_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, 0, stdout=f"{command[0]} ok\n", stderr="")


def test_local_doctor_collects_ok_checks_for_safe_repo(
    tmp_path: Path,
    monkeypatch,
) -> None:
    doctor = load_local_doctor()
    write_minimal_repo(tmp_path)
    monkeypatch.setattr(doctor.shutil, "which", lambda command: f"/usr/bin/{command}")

    checks = doctor.collect_checks(tmp_path, runner=successful_runner)

    assert not [check for check in checks if check.status == "FAIL"]
    assert any(check.name == "local .env" and check.status == "WARN" for check in checks)
    assert any(check.name == "compose config" and check.status == "OK" for check in checks)
    assert any(check.name == "audit export verifier" and check.status == "OK" for check in checks)


def test_local_doctor_fails_when_paid_llms_are_enabled_by_default(
    tmp_path: Path,
    monkeypatch,
) -> None:
    doctor = load_local_doctor()
    write_minimal_repo(tmp_path, allow_paid_llm="true")
    monkeypatch.setattr(doctor.shutil, "which", lambda command: f"/usr/bin/{command}")

    checks = doctor.collect_checks(tmp_path, runner=successful_runner)

    failure = next(check for check in checks if check.name == "env:RETOS_ALLOW_PAID_LLM")
    assert failure.status == "FAIL"
    assert "expected 'false'" in failure.detail


def test_local_doctor_render_includes_summary() -> None:
    doctor = load_local_doctor()
    rendered = doctor.render_checks(
        [
            doctor.DoctorCheck("python", "OK", "3.14.3"),
            doctor.DoctorCheck("local .env", "WARN", "missing"),
            doctor.DoctorCheck("docker", "FAIL", "missing"),
        ]
    )

    assert "RetOS local doctor" in rendered
    assert "[OK  ] python" in rendered
    assert "Summary: 1 failure(s), 1 warning(s)" in rendered
