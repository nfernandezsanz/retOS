#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = ROOT / "docs/releases/evidence/target-security-review-template.md"

REQUIRED_HEADINGS = (
    "# Target Security Review Evidence Template",
    "## Candidate",
    "## Auth And Access",
    "## Secrets And Provider Keys",
    "## Network And Runtime Exposure",
    "## Data Handling And Audit",
    "## Release Provenance",
    "## Operations And Rollback",
    "## Decision",
)

REQUIRED_FIELDS = (
    "Release version",
    "Immutable release tag",
    "Commit SHA",
    "Target environment",
    "Reviewer",
    "Review date",
    "Admin users reviewed",
    "Viewer users reviewed",
    "Domain grants reviewed",
    "Disabled accounts reviewed",
    "Password reset procedure reviewed",
    "Bootstrap admin replaced or disabled",
    "JWT issuer reviewed",
    "JWT audience reviewed",
    "JWT expiry reviewed",
    "Session/token revocation procedure reviewed",
    "`RETOS_JWT_SECRET` rotated and stored securely",
    "`RETOS_BOOTSTRAP_ADMIN_PASSWORD` removed from target secrets",
    "Database password stored in secret manager",
    "RabbitMQ password stored in secret manager",
    "Provider API keys stored in secret manager",
    "Secret-manager owner",
    "Secret rotation owner",
    "Paid-provider opt-in reviewed",
    "Paid-provider budget owner",
    "Provider rollback plan",
    "API exposure reviewed",
    "Web exposure reviewed",
    "RabbitMQ exposure reviewed",
    "Postgres exposure reviewed",
    "Ollama exposure reviewed",
    "CORS origins reviewed",
    "TLS termination reviewed",
    "Reverse proxy headers reviewed",
    "Firewall rules reviewed",
    "Docker network boundaries reviewed",
    "Mounted document sources reviewed",
    "Upload storage reviewed",
    "Eval datasets reviewed",
    "Eval reports reviewed",
    "`/audit/export` snapshot reviewed",
    "Audit hash-chain validation output",
    "Backup retention reviewed",
    "Restore rehearsal evidence linked",
    "Deletion policy reviewed",
    "Sensitive-data handling decision",
    "Current commit reviewed",
    "GitHub Actions run reviewed",
    "Backend image digest reviewed",
    "Web image digest reviewed",
    "SBOM/provenance reviewed",
    "Cosign verification output reviewed",
    "Image labels reviewed",
    "API/worker/migrate shared image ID reviewed",
    "Health checks reviewed",
    "Docker smoke evidence reviewed",
    "Upgrade procedure reviewed",
    "Backup procedure reviewed",
    "Restore procedure reviewed",
    "Rollback owner",
    "Previous image tag",
    "Rollback command reviewed",
    "Incident log location",
    "Follow-up issue owner",
    "Security decision",
    "Accepted risks",
    "Required follow-up issues",
    "Promotion impact",
)


class TargetSecurityReviewError(RuntimeError):
    pass


@dataclass(frozen=True)
class TargetSecurityReviewResult:
    headings: int
    fields: int


def _missing(required: tuple[str, ...], content: str) -> list[str]:
    return [item for item in required if item not in content]


def validate_target_security_review(
    template_path: Path = DEFAULT_TEMPLATE,
) -> TargetSecurityReviewResult:
    if not template_path.is_file():
        raise TargetSecurityReviewError(
            f"target security review template not found: {template_path}"
        )
    content = template_path.read_text(encoding="utf-8")
    if not content.strip():
        raise TargetSecurityReviewError("target security review template is empty")

    missing_headings = _missing(REQUIRED_HEADINGS, content)
    if missing_headings:
        raise TargetSecurityReviewError(
            "missing heading(s): " + ", ".join(missing_headings)
        )

    missing_fields = _missing(REQUIRED_FIELDS, content)
    if missing_fields:
        raise TargetSecurityReviewError(
            "missing review field(s): " + ", ".join(missing_fields)
        )

    if (
        "completed copy" not in content
        or "production promotion evidence" not in content
    ):
        raise TargetSecurityReviewError(
            "template must tell reviewers where the completed copy is stored"
        )

    return TargetSecurityReviewResult(
        headings=len(REQUIRED_HEADINGS),
        fields=len(REQUIRED_FIELDS),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the RetOS target security review evidence template."
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=DEFAULT_TEMPLATE,
        help="Path to docs/releases/evidence/target-security-review-template.md.",
    )
    args = parser.parse_args()
    try:
        result = validate_target_security_review(args.template)
    except TargetSecurityReviewError as exc:
        print(f"Target security review failed: {exc}", file=sys.stderr)
        return 1
    print(
        "Target security review OK: "
        f"{result.headings} heading(s), {result.fields} review field(s) verified."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
