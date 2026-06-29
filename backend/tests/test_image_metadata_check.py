from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_image_metadata.sh"
REQUIRED_FILES = (
    Path("backend/Dockerfile"),
    Path("frontend/Dockerfile"),
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


def write_fake_docker(bin_dir: Path, *, missing_web_created: bool = False) -> None:
    docker = bin_dir / "docker"
    web_created_case = (
        'if [[ "$*" == *"retos-web:local"* '
        '&& "$*" == *"org.opencontainers.image.created"* ]]; then\n'
        "  echo '<no value>'\n"
        "  exit 0\n"
        "fi"
        if missing_web_created
        else ""
    )
    docker.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                'if [[ "$1 $2" != "image inspect" ]]; then',
                "  echo 'unexpected docker command' >&2",
                "  exit 2",
                "fi",
                web_created_case,
                "echo label-value",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)


def test_image_metadata_check_passes_for_current_dockerfiles(tmp_path: Path) -> None:
    repo = copy_minimal_repo(tmp_path)

    result = run_checker(repo)

    assert result.returncode == 0, result.stderr
    assert "Image metadata source OK" in result.stdout


def test_image_metadata_check_fails_without_mit_license_label(tmp_path: Path) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(repo / "backend/Dockerfile", 'org.opencontainers.image.licenses="MIT"', "")

    result = run_checker(repo)

    assert result.returncode != 0
    assert "backend/Dockerfile missing org.opencontainers.image.licenses" in result.stderr


def test_image_metadata_check_fails_when_source_label_points_elsewhere(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(
        repo / "frontend/Dockerfile",
        'org.opencontainers.image.source="https://github.com/nfernandezsanz/retOS"',
        'org.opencontainers.image.source="https://github.com/example/fork"',
    )

    result = run_checker(repo)

    assert result.returncode != 0
    assert "frontend/Dockerfile must point labels at the public repository" in result.stderr


def test_image_metadata_check_inspects_built_images_with_fake_docker(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_docker(bin_dir)

    result = run_checker(repo, env_overrides={"RETOS_REQUIRE_BUILT_IMAGES": "1"}, bin_dir=bin_dir)

    assert result.returncode == 0, result.stderr
    assert "Image metadata inspect OK" in result.stdout


def test_image_metadata_check_fails_when_built_image_label_is_missing(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_docker(bin_dir, missing_web_created=True)

    result = run_checker(repo, env_overrides={"RETOS_REQUIRE_BUILT_IMAGES": "1"}, bin_dir=bin_dir)

    assert result.returncode != 0
    assert "retos-web:local missing org.opencontainers.image.created" in result.stderr
