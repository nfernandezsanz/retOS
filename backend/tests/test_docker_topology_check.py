from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_docker_topology.sh"
BACKEND_IMAGE = "retos-backend:local"
RUNTIME_ENVIRONMENT = {
    "RETOS_VERSION": "local",
    "RETOS_REVISION": "unknown",
    "RETOS_CREATED": "unknown",
    "RETOS_PROVIDER": "local",
}
BACKEND_VOLUMES = [
    {"type": "volume", "source": "retos_storage", "target": "/var/lib/retos/storage"},
    {"type": "volume", "source": "retos_index", "target": "/var/lib/retos/index"},
    {
        "type": "volume",
        "source": "retos_eval_datasets",
        "target": "/var/lib/retos/evals/datasets",
    },
    {
        "type": "volume",
        "source": "retos_eval_reports",
        "target": "/var/lib/retos/evals/reports",
    },
]


def compose_config(repo: Path) -> dict[str, Any]:
    api_service = {
        "image": BACKEND_IMAGE,
        "build": {
            "context": str(repo),
            "dockerfile": "backend/Dockerfile",
            "target": "backend-runtime",
        },
        "command": ["api"],
        "environment": RUNTIME_ENVIRONMENT,
        "volumes": BACKEND_VOLUMES,
        "init": True,
    }
    worker_service = {
        **api_service,
        "build": None,
        "command": ["worker"],
    }
    migrate_service = {
        "image": BACKEND_IMAGE,
        "build": None,
        "command": ["migrate"],
        "environment": RUNTIME_ENVIRONMENT,
        "init": True,
    }
    return {
        "services": {
            "api": api_service,
            "worker": worker_service,
            "migrate": migrate_service,
        }
    }


def write_fake_docker(bin_dir: Path, config_path: Path) -> None:
    docker = bin_dir / "docker"
    docker.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                'if [[ "$1" != "compose" ]]; then',
                "  echo 'unexpected docker command' >&2",
                "  exit 2",
                "fi",
                f"cat {str(config_path)!r}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)


def write_minimal_repo(tmp_path: Path, config: dict[str, Any]) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    bin_dir = tmp_path / "bin"
    repo.mkdir()
    bin_dir.mkdir()
    (repo / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (repo / ".env.example").write_text("RETOS_IMAGE_TAG=local\n", encoding="utf-8")
    config_path = tmp_path / "compose-config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    write_fake_docker(bin_dir, config_path)
    return repo, bin_dir


def run_checker(repo: Path, bin_dir: Path) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "RETOS_COMPOSE_FILE": "docker-compose.yml",
        "RETOS_COMPOSE_ENV_FILE": ".env.example",
    }
    return subprocess.run(  # noqa: S603
        ["/bin/bash", str(CHECKER)],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_docker_topology_check_passes_for_shared_backend_config(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    config = compose_config(repo)
    repo, bin_dir = write_minimal_repo(tmp_path, config)

    result = run_checker(repo, bin_dir)

    assert result.returncode == 0, result.stderr
    assert "Docker topology OK" in result.stdout


def test_docker_topology_check_fails_when_worker_uses_different_image(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    config = compose_config(repo)
    config["services"]["worker"]["image"] = "retos-worker:local"
    repo, bin_dir = write_minimal_repo(tmp_path, config)

    result = run_checker(repo, bin_dir)

    assert result.returncode != 0
    assert "Backend roles must share one image" in result.stderr


def test_docker_topology_check_fails_when_worker_declares_build(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    config = compose_config(repo)
    config["services"]["worker"]["build"] = {
        "context": str(repo),
        "dockerfile": "backend/Dockerfile",
        "target": "backend-runtime",
    }
    repo, bin_dir = write_minimal_repo(tmp_path, config)

    result = run_checker(repo, bin_dir)

    assert result.returncode != 0
    assert "Only api may build the shared backend image" in result.stderr


def test_docker_topology_check_fails_when_backend_target_changes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    config = compose_config(repo)
    config["services"]["api"]["build"]["target"] = "api-runtime"
    repo, bin_dir = write_minimal_repo(tmp_path, config)

    result = run_checker(repo, bin_dir)

    assert result.returncode != 0
    assert "must target backend-runtime" in result.stderr


def test_docker_topology_check_fails_when_worker_loses_state_volume(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    config = compose_config(repo)
    config["services"]["worker"]["volumes"] = BACKEND_VOLUMES[:-1]
    repo, bin_dir = write_minimal_repo(tmp_path, config)

    result = run_checker(repo, bin_dir)

    assert result.returncode != 0
    assert "API and worker must share the same runtime context for volumes" in result.stderr
