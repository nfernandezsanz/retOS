from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_release_workflow.sh"
REQUIRED_FILES = (
    Path(".github/workflows/release.yml"),
    Path("docs/docker.md"),
    Path("docs/operations.md"),
    Path("docs/release-process.md"),
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


def test_release_workflow_check_passes_for_current_contract(tmp_path: Path) -> None:
    repo = copy_minimal_repo(tmp_path)

    result = run_checker(repo)

    assert result.returncode == 0, result.stderr
    assert "Release workflow OK" in result.stdout


def test_release_workflow_check_fails_without_cosign_signing_step(tmp_path: Path) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(repo / ".github/workflows/release.yml", "cosign sign --yes", "cosign attest --yes")

    result = run_checker(repo)

    assert result.returncode != 0
    assert "release.yml missing cosign sign --yes" in result.stderr


def test_release_workflow_check_fails_without_frontend_format_gate(tmp_path: Path) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(
        repo / ".github/workflows/release.yml",
        "npm run format:check",
        "npm run check:format",
    )

    result = run_checker(repo)

    assert result.returncode != 0
    assert "release.yml missing npm run format:check" in result.stderr


def test_release_workflow_check_fails_when_worker_image_is_published(tmp_path: Path) -> None:
    repo = copy_minimal_repo(tmp_path)
    workflow = repo / ".github/workflows/release.yml"
    workflow.write_text(
        workflow.read_text(encoding="utf-8")
        + "\n# Regression fixture: ghcr.io/${{ github.repository_owner }}/retos-worker\n",
        encoding="utf-8",
    )

    result = run_checker(repo)

    assert result.returncode != 0
    assert "must not publish a separate worker image" in result.stderr


def test_release_workflow_check_fails_without_release_process_cosign_docs(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(repo / "docs/release-process.md", "Cosign", "Signature tool")

    result = run_checker(repo)

    assert result.returncode != 0
    assert "docs/release-process.md missing release publishing phrase: Cosign" in result.stderr
