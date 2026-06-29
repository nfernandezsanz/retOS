from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_production_preflight.sh"
REQUIRED_FILES = (
    Path("docs/production-readiness.md"),
    Path("docs/branding.md"),
    Path("docs/releases/2026.06.28-alpha.1.md"),
    Path("planning/04-process-tracker.md"),
    Path(".github/workflows/ci.yml"),
    Path(".github/workflows/release.yml"),
)
SHELL_SUBCHECKS = (
    "check_release_readiness.sh",
    "check_ci_workflow.sh",
    "check_audit_pack.sh",
    "check_release_notes.sh",
    "check_versioned_release_notes.sh",
    "check_release_workflow.sh",
    "check_branding_assets.sh",
)
PYTHON_SUBCHECKS = (
    "check_readme_usability.py",
    "check_visual_review.py",
)


def copy_minimal_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    for relative in REQUIRED_FILES:
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)

    scripts_dir = repo / "scripts"
    scripts_dir.mkdir()
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


def test_production_preflight_check_passes_for_current_contract(tmp_path: Path) -> None:
    repo = copy_minimal_repo(tmp_path)

    result = run_checker(repo)

    assert result.returncode == 0, result.stderr
    assert "Production preflight OK" in result.stdout


def test_production_preflight_check_fails_when_pytest_count_drifts(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(
        repo / "docs" / "production-readiness.md",
        "723 pytest cases",
        "722 pytest cases",
    )

    result = run_checker(repo)

    assert result.returncode != 0
    assert "current backend pytest case count" in result.stderr


def test_production_preflight_check_fails_when_release_workflow_loses_gate(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(
        repo / ".github" / "workflows" / "release.yml",
        "make production-preflight",
        "make release-check",
    )

    result = run_checker(repo)

    assert result.returncode != 0
    assert "release workflow must run the production preflight" in result.stderr


def test_production_preflight_check_fails_when_external_blockers_are_removed(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(
        repo / "planning" / "04-process-tracker.md", "Final release promotion", "Release promotion"
    )

    result = run_checker(repo)

    assert result.returncode != 0
    assert "process tracker must keep final release blockers visible" in result.stderr


def test_production_preflight_check_propagates_subcheck_failures(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    failing_subcheck = repo / "scripts" / "check_audit_pack.sh"
    failing_subcheck.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\necho audit-pack-boom >&2\nexit 9\n",
        encoding="utf-8",
    )
    failing_subcheck.chmod(0o755)

    result = run_checker(repo)

    assert result.returncode == 9
    assert "audit-pack-boom" in result.stderr
