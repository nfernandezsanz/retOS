from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_published_release_evidence.sh"
VALID_BACKEND_DIGEST = "sha256:" + "a" * 64
VALID_WEB_DIGEST = "sha256:" + "b" * 64


def run_checker(overrides: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "VERSION": "2026.06.28-alpha.1",
        "BACKEND_DIGEST": VALID_BACKEND_DIGEST,
        "WEB_DIGEST": VALID_WEB_DIGEST,
        "RETOS_RELEASE_EVIDENCE_DRY_RUN": "1",
        **overrides,
    }
    return subprocess.run(  # noqa: S603
        ["/bin/bash", str(CHECKER)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_published_release_evidence_check_accepts_dry_run_inputs() -> None:
    result = run_checker({})

    assert result.returncode == 0, result.stderr
    assert "Published release evidence OK" in result.stdout
    assert "DRY RUN: cosign verify" in result.stdout
    assert "DRY RUN: docker buildx imagetools inspect" in result.stdout
    assert "Immutable tags resolve to the recorded digests" in result.stdout


def test_published_release_evidence_check_rejects_latest_version() -> None:
    result = run_checker({"VERSION": "latest"})

    assert result.returncode != 0
    assert "VERSION must look like" in result.stderr


def test_published_release_evidence_check_rejects_local_version() -> None:
    result = run_checker({"VERSION": "local"})

    assert result.returncode != 0
    assert "VERSION must look like" in result.stderr


def test_published_release_evidence_check_rejects_bad_digest() -> None:
    result = run_checker({"BACKEND_DIGEST": "sha256:ABC"})

    assert result.returncode != 0
    assert "BACKEND_DIGEST must look like sha256:<64 lowercase hex chars>" in result.stderr


def test_published_release_evidence_check_rejects_non_ghcr_image() -> None:
    result = run_checker({"BACKEND_IMAGE": "docker.io/nfernandezsanz/retos-backend"})

    assert result.returncode != 0
    assert "must use ghcr.io" in result.stderr
