#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = ROOT / "docs/releases/evidence/production-promotion-template.md"

REQUIRED_HEADINGS = (
    "# Production Promotion Evidence Template",
    "## Candidate",
    "## Machine Evidence",
    "## Release Provenance",
    "## Visual Review",
    "## Backup And Restore Rehearsal",
    "## Security Review",
    "## Rollback",
    "## Decision",
)

REQUIRED_MACHINE_GATES = (
    "make ci-status-check",
    "make local-acceptance",
    "make check",
    "make dependency-audit",
    "make security-policy-check",
    "make target-security-review-check",
    "make env-security-check",
    "make ignore-hygiene-check",
    "make operations-runbook-check",
    "make promotion-template-check",
    "make integration",
    "make frontend-test",
    "make frontend-e2e",
    "make frontend-visual-audit",
    "make visual-audit-check",
    "make visual-review-check",
    "docker compose --env-file .env.example config",
    "docker compose --dry-run build",
    "make docker-smoke",
    "make release-check",
    "make production-preflight",
    "make calibration-scope-decision-check",
    "make auditor-static-check",
    "make audit-manifest-check",
    "make audit-handoff-report",
    "make audit-bundle",
    "make audit-bundle-check",
    "make audit-export-check",
    "make release-evidence-check",
)

REQUIRED_FIELDS = (
    "Release version",
    "Immutable release tag",
    "Commit SHA",
    "GitHub Actions run",
    "Backend image digest",
    "Web image digest",
    "Target environment",
    "GHCR backend digest recorded",
    "GHCR web digest recorded",
    "SBOM/provenance attestation links",
    "Cosign signature verification output",
    "API, worker, and migrate share one backend image ID",
    "Desktop visual audit PNG reviewed",
    "Mobile visual audit PNG reviewed",
    "`make visual-audit-check` output",
    "Visual review template completed",
    "Visual review evidence link",
    "Visual review decision",
    "UI issues accepted or filed",
    "Backup timestamp",
    "Backup artifact path",
    "Postgres dump created",
    "Storage archive created",
    "Eval reports archive created",
    "Eval datasets archive created",
    "Restore rehearsed in disposable environment",
    "Migrations rerun after restore",
    "Health checks after restore",
    "Development secrets replaced",
    "`make env-security-check` output",
    "`RETOS_JWT_SECRET` rotated and stored securely",
    "Bootstrap admin replaced or disabled",
    "CORS origins reviewed",
    "API/web/RabbitMQ/Postgres/Ollama exposure reviewed",
    "Target security review template completed",
    "Provider keys stored in secret manager",
    "Paid-provider budget owner recorded",
    "`/audit/export` hash-chain snapshot reviewed",
    "Calibration scope decision template completed",
    "Rollback owner",
    "Rollback command rehearsed",
    "Data restore trigger criteria",
    "Promotion decision",
    "Accepted scope limits",
    "Required follow-up issues",
)


class PromotionTemplateError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromotionTemplateResult:
    headings: int
    gates: int
    fields: int


def _missing(required: tuple[str, ...], content: str) -> list[str]:
    return [item for item in required if item not in content]


def validate_promotion_template(
    template_path: Path = DEFAULT_TEMPLATE,
) -> PromotionTemplateResult:
    if not template_path.is_file():
        raise PromotionTemplateError(f"promotion template not found: {template_path}")
    content = template_path.read_text(encoding="utf-8")
    if not content.strip():
        raise PromotionTemplateError("promotion template is empty")

    missing_headings = _missing(REQUIRED_HEADINGS, content)
    if missing_headings:
        raise PromotionTemplateError(
            "missing heading(s): " + ", ".join(missing_headings)
        )

    missing_gates = _missing(REQUIRED_MACHINE_GATES, content)
    if missing_gates:
        raise PromotionTemplateError(
            "missing machine gate(s): " + ", ".join(missing_gates)
        )

    missing_fields = _missing(REQUIRED_FIELDS, content)
    if missing_fields:
        raise PromotionTemplateError(
            "missing review field(s): " + ", ".join(missing_fields)
        )

    if "versioned release note or the release record" not in content:
        raise PromotionTemplateError(
            "template must tell reviewers where the completed copy is stored"
        )

    return PromotionTemplateResult(
        headings=len(REQUIRED_HEADINGS),
        gates=len(REQUIRED_MACHINE_GATES),
        fields=len(REQUIRED_FIELDS),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the RetOS production promotion evidence template."
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=DEFAULT_TEMPLATE,
        help="Path to docs/releases/evidence/production-promotion-template.md.",
    )
    args = parser.parse_args()
    try:
        result = validate_promotion_template(args.template)
    except PromotionTemplateError as exc:
        print(f"Promotion template failed: {exc}", file=sys.stderr)
        return 1
    print(
        "Promotion template OK: "
        f"{result.headings} heading(s), {result.gates} machine gate(s), "
        f"{result.fields} review field(s) verified."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
