from __future__ import annotations

import argparse
import asyncio

from retos.core.config import get_settings
from retos.demo.seed import DEMO_DOMAIN_SLUG, DEMO_SOURCE_URI, DemoSeedResult, run_seed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed a local RetOS database with an auditable demo corpus."
    )
    parser.add_argument("--domain-slug", default=DEMO_DOMAIN_SLUG)
    parser.add_argument("--domain-name", default="RetOS Demo")
    parser.add_argument("--source-name", default="Local demo fixtures")
    parser.add_argument("--source-uri", default=DEMO_SOURCE_URI)
    parser.add_argument(
        "--create-schema",
        action="store_true",
        help="Create tables before seeding. Useful for isolated SQLite smoke runs.",
    )
    parser.add_argument(
        "--skip-index",
        action="store_true",
        help="Seed documents without rebuilding the local BM25 projection.",
    )
    return parser.parse_args()


def render_result(result: DemoSeedResult) -> str:
    lines = [
        "RetOS demo seed complete",
        f"Domain: {result.domain_id}",
        f"Source: {result.source_id}",
        f"Documents: {result.created_documents} created, {result.skipped_documents} skipped",
        f"Index: {result.indexed_segments} segments",
    ]
    if result.index_job_id is not None:
        lines.append(f"Index job: {result.index_job_id}")
    lines.append("Try search: Apollo guidance")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    settings = get_settings()
    result = asyncio.run(
        run_seed(
            settings=settings,
            domain_slug=args.domain_slug,
            domain_name=args.domain_name,
            source_name=args.source_name,
            source_uri=args.source_uri,
            create_tables=args.create_schema,
            rebuild_index=not args.skip_index,
        )
    )
    print(render_result(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
