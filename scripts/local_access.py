#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from check_env_security import parse_env  # noqa: E402

DEFAULT_ADMIN_EMAIL = "admin@retos.dev"
DEFAULT_ADMIN_PASSWORD = "retos-dev-admin-change-me"


def env_value(env: dict[str, str], key: str, default: str) -> str:
    value = env.get(key, "").strip()
    return value or default


def password_detail(env: dict[str, str]) -> str:
    password = env_value(
        env,
        "RETOS_BOOTSTRAP_ADMIN_PASSWORD",
        DEFAULT_ADMIN_PASSWORD,
    )
    if password == DEFAULT_ADMIN_PASSWORD:
        return password
    return "configured in .env; not printed"


def render_local_access(root: Path = ROOT) -> str:
    env_path = root / ".env"
    env = parse_env(env_path if env_path.is_file() else root / ".env.example")
    source = ".env" if env_path.is_file() else ".env.example"
    admin_email = env_value(env, "RETOS_BOOTSTRAP_ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL)
    lines = [
        "RetOS local access",
        f"Config source: {source}",
        "URLs:",
        "  Console:   http://localhost:8080",
        "  API docs:  http://localhost:8000/docs",
        "  Readiness: http://localhost:8000/readyz",
        "  RabbitMQ:  http://localhost:15672",
        "Bootstrap admin:",
        f"  Email:    {admin_email}",
        f"  Password: {password_detail(env)}",
        "Safety:",
        "  This command only prints the development placeholder password.",
        "  Custom local passwords stay in .env and are not echoed.",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print local RetOS URLs and safe development access hints."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Repository root. Defaults to the current RetOS checkout.",
    )
    args = parser.parse_args()
    print(render_local_access(args.root.resolve()))


if __name__ == "__main__":
    main()
