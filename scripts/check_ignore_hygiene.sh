#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
from __future__ import annotations

from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Ignore hygiene failed: {message}")


def lines(path: Path) -> set[str]:
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


gitignore_path = Path(".gitignore")
dockerignore_path = Path(".dockerignore")
docker_docs_path = Path("docs/docker.md")
operations_path = Path("docs/operations.md")

for path in (gitignore_path, dockerignore_path, docker_docs_path, operations_path):
    require(path.is_file() and path.stat().st_size > 0, f"missing or empty {path}")

gitignore = lines(gitignore_path)
dockerignore = lines(dockerignore_path)
docker_docs = docker_docs_path.read_text(encoding="utf-8")
operations = operations_path.read_text(encoding="utf-8")

required_gitignore = {
    ".env",
    ".env.*",
    "!.env.example",
    ".venv/",
    "node_modules/",
    "frontend/dist/",
    "frontend/coverage/",
    "frontend/playwright-report/",
    "frontend/test-results/",
    "backend/coverage.json",
    "backend/.pytest_cache/",
    "backend/.mypy_cache/",
    "backend/.ruff_cache/",
    "retos_storage/",
    "retos_index/",
    "retos_uploads/",
    "retos_ollama/",
    "retos_postgres/",
    "retos_rabbitmq/",
    "retos_tmp/",
    "evals/datasets/",
    "evals/cache/",
    "evals/reports/",
    "docker-compose.override.yml",
    "logs/",
    "tmp/",
    "temp/",
    ".cache/",
    "backups/",
}

required_dockerignore = {
    ".git",
    ".github",
    ".gitignore",
    ".env",
    ".env.*",
    "!.env.example",
    ".venv",
    "node_modules",
    "frontend/node_modules",
    "frontend/dist",
    "frontend/coverage",
    "frontend/playwright-report",
    "frontend/test-results",
    "backend/coverage.json",
    "backend/.pytest_cache",
    "backend/.mypy_cache",
    "backend/.ruff_cache",
    "retos_storage",
    "retos_index",
    "retos_uploads",
    "retos_ollama",
    "retos_postgres",
    "retos_rabbitmq",
    "retos_tmp",
    "evals/datasets",
    "evals/cache",
    "evals/reports",
    "backups",
    "backend/tests",
    "planning",
    "docs",
}

missing_gitignore = sorted(required_gitignore - gitignore)
missing_dockerignore = sorted(required_dockerignore - dockerignore)
require(not missing_gitignore, f".gitignore missing: {', '.join(missing_gitignore)}")
require(not missing_dockerignore, f".dockerignore missing: {', '.join(missing_dockerignore)}")

for phrase in (
    ".dockerignore",
    "secrets",
    "local volumes",
    "virtualenvs",
    "caches",
    "coverage reports",
    "public dataset samples",
    "generated reports",
    "local backups",
    "frontend",
    "assets",
):
    require(phrase in docker_docs, f"docs/docker.md missing ignore guidance phrase: {phrase}")

require("backup_dir=\"backups/" in operations, "docs/operations.md must document local backups under backups/")

print("Ignore hygiene OK: secrets, generated files, local volumes, datasets, and backups stay out of Git and Docker contexts.")
PY
