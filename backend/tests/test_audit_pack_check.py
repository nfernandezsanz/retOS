from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_audit_pack.sh"
REQUIRED_FILES = (
    Path("docs/production-readiness.md"),
    Path("README.md"),
    Path("docs/operations.md"),
    Path("docs/release-process.md"),
    Path("planning/04-process-tracker.md"),
    Path("docs/releases/2026.06.28-alpha.1.md"),
    Path("docs/releases/evidence/calibration-scope-decision-template.md"),
    Path("docs/releases/evidence/backup-restore-drill-template.md"),
    Path("docs/releases/evidence/target-security-review-template.md"),
    Path("docs/releases/evidence/visual-review-template.md"),
    Path("docs/releases/evidence/production-promotion-template.md"),
    Path(".github/workflows/ci.yml"),
    Path("scripts/check_ci_status.sh"),
    Path("scripts/check_dependency_audit.sh"),
    Path("scripts/check_security_policy.sh"),
    Path("scripts/check_ignore_hygiene.sh"),
    Path("scripts/check_calibration_scope_decision.py"),
    Path("scripts/check_backup_restore_drill.py"),
    Path("scripts/check_target_security_review.py"),
    Path("scripts/check_visual_review.py"),
    Path("scripts/check_promotion_template.py"),
    Path("SECURITY.md"),
    Path("scripts/export_audit_manifest.py"),
)


def copy_minimal_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    for relative in REQUIRED_FILES:
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    return repo


def run_checker(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ["/bin/bash", str(CHECKER)],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )


def replace_text(path: Path, old: str, new: str) -> None:
    content = path.read_text(encoding="utf-8")
    assert old in content
    path.write_text(content.replace(old, new), encoding="utf-8")


def test_audit_pack_check_passes_for_current_contract(tmp_path: Path) -> None:
    repo = copy_minimal_repo(tmp_path)

    result = run_checker(repo)

    assert result.returncode == 0, result.stderr
    assert "Audit pack OK" in result.stdout


def test_audit_pack_check_fails_without_local_acceptance_gate(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(
        repo / "docs" / "production-readiness.md",
        "make local-acceptance",
        "make preflight-local",
    )

    result = run_checker(repo)

    assert result.returncode != 0
    assert (
        "docs/production-readiness.md missing evidence phrase: make local-acceptance"
        in result.stderr
    )


def test_audit_pack_check_fails_when_release_note_loses_publish_blockers(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(
        repo / "docs" / "releases" / "2026.06.28-alpha.1.md",
        "Publishing evidence still required",
        "Publishing evidence recorded",
    )

    result = run_checker(repo)

    assert result.returncode != 0
    assert "release note must keep publish evidence blockers explicit" in result.stderr


def test_audit_pack_check_fails_when_ci_manifest_artifact_is_removed(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(
        repo / ".github" / "workflows" / "ci.yml",
        "retos-audit-manifest-${{ github.sha }}",
        "retos-audit-summary-${{ github.sha }}",
    )

    result = run_checker(repo)

    assert result.returncode != 0
    assert "CI must publish audit manifest evidence" in result.stderr


def test_audit_pack_check_fails_when_promotion_template_loses_visual_review(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(
        repo / "docs" / "releases" / "evidence" / "production-promotion-template.md",
        "Visual review decision",
        "UI decision",
    )

    result = run_checker(repo)

    assert result.returncode != 0
    assert "promotion evidence template missing visual review field" in result.stderr


def test_audit_pack_check_fails_when_ci_status_artifact_checks_drift(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(
        repo / "scripts" / "check_ci_status.sh",
        "retos-audit-handoff-{sha}",
        "retos-audit-summary-{sha}",
    )

    result = run_checker(repo)

    assert result.returncode != 0
    assert "CI status check must validate required artifacts" in result.stderr
