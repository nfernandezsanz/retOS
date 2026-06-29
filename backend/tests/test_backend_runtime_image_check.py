from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_backend_runtime_image.sh"


def write_fake_docker(
    bin_dir: Path,
    *,
    missing_role: str | None = None,
    worker_image: str = "sha256:backend-runtime",
) -> None:
    docker = bin_dir / "docker"
    docker.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                'joined="$*"',
                'if [[ "$1" == "compose" ]]; then',
                '  if [[ "${RETOS_FAKE_REQUIRE_ENV_FILE:-0}" == "1" ]] '
                '&& [[ "$joined" != *"--env-file .env.test"* ]]; then',
                "    echo 'expected compose env file' >&2",
                "    exit 2",
                "  fi",
                '  role="${@: -1}"',
                f"  if [[ \"$role\" == \"{missing_role or '__none__'}\" ]]; then",
                "    exit 0",
                "  fi",
                '  case "$role" in',
                "    api) echo container-api ;;",
                "    worker) echo container-worker ;;",
                "    migrate) echo container-migrate ;;",
                '    *) echo "unexpected compose role: $role" >&2; exit 2 ;;',
                "  esac",
                "  exit 0",
                "fi",
                'if [[ "$1" == "inspect" ]]; then',
                '  container="${@: -1}"',
                '  case "$container" in',
                "    container-api) echo sha256:backend-runtime ;;",
                f"    container-worker) echo {worker_image} ;;",
                "    container-migrate) echo sha256:backend-runtime ;;",
                '    *) echo "unexpected inspect target: $container" >&2; exit 2 ;;',
                "  esac",
                "  exit 0",
                "fi",
                "echo 'unexpected docker command' >&2",
                "exit 2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)


def run_checker(
    repo: Path,
    bin_dir: Path,
    *,
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "RETOS_COMPOSE_ENV_FILE": ".env.test",
        "RETOS_DOCKER_PROJECT": "retos-test",
        **(env_overrides or {}),
    }
    return subprocess.run(  # noqa: S603
        ["/bin/bash", str(CHECKER)],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_backend_runtime_image_check_passes_when_roles_share_image(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_docker(bin_dir)

    result = run_checker(
        tmp_path,
        bin_dir,
        env_overrides={"RETOS_FAKE_REQUIRE_ENV_FILE": "1"},
    )

    assert result.returncode == 0, result.stderr
    assert "Backend runtime image OK" in result.stdout
    assert "sha256:backend-runtime" in result.stdout


def test_backend_runtime_image_check_fails_when_worker_container_is_missing(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_docker(bin_dir, missing_role="worker")

    result = run_checker(tmp_path, bin_dir)

    assert result.returncode != 0
    assert "Missing container for backend role 'worker'" in result.stderr


def test_backend_runtime_image_check_fails_when_worker_uses_different_image(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_docker(bin_dir, worker_image="sha256:worker-runtime")

    result = run_checker(tmp_path, bin_dir)

    assert result.returncode != 0
    assert "Backend roles must run the exact same image ID" in result.stderr
    assert "worker: sha256:worker-runtime" in result.stderr


def test_backend_runtime_image_check_can_run_without_compose_env_file(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_docker(bin_dir)

    result = run_checker(
        tmp_path,
        bin_dir,
        env_overrides={
            "RETOS_DOCKER_USE_ENV_FILE": "0",
            "RETOS_FAKE_REQUIRE_ENV_FILE": "0",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "Backend runtime image OK" in result.stdout
