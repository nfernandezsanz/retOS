from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_release_readiness.sh"
REQUIRED_FILES = (
    Path("README.md"),
    Path("docs/docker.md"),
    Path("docs/operations.md"),
    Path("docs/api-integration.md"),
    Path("docs/evals.md"),
    Path("docs/database.md"),
    Path("CONTRIBUTING.md"),
    Path("SECURITY.md"),
    Path("LICENSE"),
    Path("CHANGELOG.md"),
    Path("Makefile"),
    Path("docs/releases/README.md"),
    Path("docs/releases/2026.06.28-alpha.1.md"),
    Path("docs/releases/evidence/calibration-scope-decision-template.md"),
    Path("docs/releases/evidence/backup-restore-drill-template.md"),
    Path("docs/releases/evidence/production-promotion-template.md"),
    Path("docs/releases/evidence/target-security-review-template.md"),
    Path("docs/releases/evidence/visual-review-template.md"),
    Path(".env.example"),
    Path("docker-compose.yml"),
    Path(".gitignore"),
    Path(".dockerignore"),
    Path("docs/release-process.md"),
    Path("docs/production-readiness.md"),
    Path("scripts/check_published_release_evidence.sh"),
)
SHELL_SUBCHECKS = (
    "check_ci_workflow.sh",
    "check_production_preflight.sh",
    "check_docker_topology.sh",
    "check_image_metadata.sh",
    "check_image_size.sh",
    "check_release_workflow.sh",
    "check_release_notes.sh",
    "check_versioned_release_notes.sh",
    "check_audit_pack.sh",
    "check_branding_assets.sh",
    "check_security_policy.sh",
    "check_ignore_hygiene.sh",
    "check_operations_runbook.sh",
)
PYTHON_SUBCHECKS = (
    "check_readme_usability.py",
    "check_visual_review.py",
    "check_env_security.py",
    "check_backup_restore_drill.py",
    "check_promotion_template.py",
    "check_target_security_review.py",
    "check_calibration_scope_decision.py",
    "check_eval_calibration_evidence.py",
    "check_eval_calibration_trend.py",
    "check_visual_audit.py",
    "export_audit_manifest.py",
    "check_audit_manifest.py",
    "export_audit_bundle.py",
    "check_audit_bundle.py",
)


def copy_minimal_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    for relative in REQUIRED_FILES:
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
        if target.suffix == ".sh":
            target.chmod(0o755)

    scripts_dir = repo / "scripts"
    scripts_dir.mkdir(exist_ok=True)
    for script in SHELL_SUBCHECKS:
        path = scripts_dir / script
        path.write_text("#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n", encoding="utf-8")
        path.chmod(0o755)
    for script in PYTHON_SUBCHECKS:
        (scripts_dir / script).write_text("from __future__ import annotations\n", encoding="utf-8")
    return repo


def run_checker(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ["/bin/bash", str(CHECKER)],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        env=os.environ,
    )


def replace_text(path: Path, old: str, new: str) -> None:
    content = path.read_text(encoding="utf-8")
    assert old in content
    path.write_text(content.replace(old, new), encoding="utf-8")


def test_release_readiness_check_passes_for_current_contract(tmp_path: Path) -> None:
    repo = copy_minimal_repo(tmp_path)

    result = run_checker(repo)

    assert result.returncode == 0, result.stderr
    assert "Release readiness OK" in result.stdout


def test_release_readiness_check_fails_when_required_file_is_missing(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    (repo / "docs" / "docker.md").unlink()

    result = run_checker(repo)

    assert result.returncode != 0
    assert "missing or empty docs/docker.md" in result.stderr


def test_release_readiness_check_fails_when_paid_llms_are_enabled_by_default(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(repo / ".env.example", "RETOS_ALLOW_PAID_LLM=false", "RETOS_ALLOW_PAID_LLM=true")

    result = run_checker(repo)

    assert result.returncode != 0
    assert "paid LLMs must be disabled by default" in result.stderr


def test_release_readiness_check_fails_when_operations_loses_ghcr_evidence(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(repo / "docs" / "operations.md", "GHCR", "Container registry")

    result = run_checker(repo)

    assert result.returncode != 0
    assert "docs/operations.md missing operational phrase: GHCR" in result.stderr


def test_release_readiness_check_fails_when_local_acceptance_loses_docker_smoke(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(repo / "Makefile", " docker-smoke", " docker-check")

    result = run_checker(repo)

    assert result.returncode != 0
    assert "local-acceptance must depend on docker-smoke" in result.stderr


def test_release_readiness_check_propagates_subcheck_failures(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    failing_subcheck = repo / "scripts" / "check_release_workflow.sh"
    failing_subcheck.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\necho release-workflow-boom >&2\nexit 7\n",
        encoding="utf-8",
    )
    failing_subcheck.chmod(0o755)

    result = run_checker(repo)

    assert result.returncode == 7
    assert "release-workflow-boom" in result.stderr
