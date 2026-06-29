from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_image_size.sh"
REQUIRED_FILES = (
    Path("docs/docker.md"),
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


def run_checker(
    repo: Path,
    *,
    env_overrides: dict[str, str] | None = None,
    bin_dir: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        **(env_overrides or {}),
    }
    if bin_dir is not None:
        env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    return subprocess.run(  # noqa: S603
        ["/bin/bash", str(CHECKER)],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def replace_text(path: Path, old: str, new: str) -> None:
    content = path.read_text(encoding="utf-8")
    assert old in content
    path.write_text(content.replace(old, new), encoding="utf-8")


def write_fake_docker(
    bin_dir: Path,
    *,
    backend_size: int = 1_200_000_000,
    web_size: int = 90_000_000,
) -> None:
    docker = bin_dir / "docker"
    docker.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                'if [[ "$1 $2" != "image inspect" ]]; then',
                "  echo 'unexpected docker command' >&2",
                "  exit 2",
                "fi",
                'if [[ "$*" == *"retos-backend:local"* ]]; then',
                f"  echo {backend_size}",
                "  exit 0",
                "fi",
                'if [[ "$*" == *"retos-web:local"* ]]; then',
                f"  echo {web_size}",
                "  exit 0",
                "fi",
                "echo 'unexpected image' >&2",
                "exit 2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)


def test_image_size_check_passes_for_current_docs_and_budgets(tmp_path: Path) -> None:
    repo = copy_minimal_repo(tmp_path)

    result = run_checker(repo)

    assert result.returncode == 0, result.stderr
    assert "Image size source OK" in result.stdout


def test_image_size_check_rejects_non_integer_backend_budget(tmp_path: Path) -> None:
    repo = copy_minimal_repo(tmp_path)

    result = run_checker(
        repo,
        env_overrides={"RETOS_BACKEND_IMAGE_MAX_BYTES": "1.4gb"},
    )

    assert result.returncode != 0
    assert "RETOS_BACKEND_IMAGE_MAX_BYTES must be a positive integer" in result.stderr


def test_image_size_check_rejects_too_small_backend_budget(tmp_path: Path) -> None:
    repo = copy_minimal_repo(tmp_path)

    result = run_checker(
        repo,
        env_overrides={"RETOS_BACKEND_IMAGE_MAX_BYTES": "999999999"},
    )

    assert result.returncode != 0
    assert "backend budget should leave room" in result.stderr


def test_image_size_check_fails_when_release_docs_lose_budget_reference(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(
        repo / "docs" / "release-process.md",
        "RETOS_WEB_IMAGE_MAX_BYTES",
        "RETOS_WEB_BYTES_LIMIT",
    )

    result = run_checker(repo)

    assert result.returncode != 0
    assert "docs/release-process.md missing RETOS_WEB_IMAGE_MAX_BYTES" in result.stderr


def test_image_size_check_inspects_built_images_with_fake_docker(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_docker(bin_dir)

    result = run_checker(
        repo,
        env_overrides={"RETOS_REQUIRE_BUILT_IMAGES": "1"},
        bin_dir=bin_dir,
    )

    assert result.returncode == 0, result.stderr
    assert "Image size OK: retos-backend:local" in result.stdout
    assert "Image size OK: retos-web:local" in result.stdout


def test_image_size_check_fails_when_built_image_exceeds_limit(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_docker(bin_dir, web_size=210_000_000)

    result = run_checker(
        repo,
        env_overrides={"RETOS_REQUIRE_BUILT_IMAGES": "1"},
        bin_dir=bin_dir,
    )

    assert result.returncode != 0
    assert "retos-web:local" in result.stderr
    assert "exceeds" in result.stderr
