#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
from __future__ import annotations

from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Auditor evidence matrix failed: {message}")


paths = {
    "matrix": Path("docs/auditor-evidence-matrix.md"),
    "readme": Path("README.md"),
    "production": Path("docs/production-readiness.md"),
    "tracker": Path("planning/04-process-tracker.md"),
    "makefile": Path("Makefile"),
    "ci": Path(".github/workflows/ci.yml"),
}

for name, path in paths.items():
    require(path.is_file() and path.stat().st_size > 0, f"missing or empty {name}: {path}")

matrix = paths["matrix"].read_text(encoding="utf-8")
readme = paths["readme"].read_text(encoding="utf-8")
production = paths["production"].read_text(encoding="utf-8")
tracker = paths["tracker"].read_text(encoding="utf-8")
makefile = paths["makefile"].read_text(encoding="utf-8")
ci = paths["ci"].read_text(encoding="utf-8")

for heading in (
    "# Auditor Evidence Matrix",
    "## Requirement Trace",
    "## Auditor Decision Rule",
):
    require(heading in matrix, f"matrix missing {heading}")

for requirement in (
    "Friendly document and domain management UI",
    "Friendly query UI",
    "Switchable local and paid LLM providers",
    "Deep Agents runtime, not a classic LangGraph harness",
    "Auditable journals and traces",
    "SSE visibility for long processing",
    "Docker-first reusable images",
    "Celery with RabbitMQ",
    "90% or better test coverage",
    "Integration tests against real endpoints and UI",
    "Single local pre-audit acceptance gate",
    "Evals and calibration",
    "Branding, colors, and project image",
    "Open source hygiene",
    "Release and production handoff",
):
    require(requirement in matrix, f"matrix missing requirement row: {requirement}")

for gate in (
    "make check",
    "make env-security-check",
    "make local-acceptance",
    "make api-smoke",
    "make eval-agent-multihop",
    "make eval-calibration-gate",
    "make eval-calibration-trend-gate",
    "make audit-manifest-check",
    "make audit-export-check",
    "make frontend-e2e",
    "make frontend-visual-audit",
    "make visual-audit-check",
    "make docker-smoke",
    "make integration",
    "make auditor-static-check",
    "make release-check",
    "make production-preflight",
):
    require(gate in matrix, f"matrix missing local gate: {gate}")

for phrase in (
    "RetOS is not production-promoted yet",
    "compact document context cards",
    "visible document/archive scope",
    "registered source count",
    "local rebuild posture",
    "tag publish",
    "real digests",
    "SBOM/provenance",
    "Cosign evidence",
    "target-environment review",
    "Ollama `gemma4`",
    "95.42%",
    "90.75%",
):
    require(phrase in matrix, f"matrix missing audit phrase: {phrase}")

for linked_doc, content in (
    ("README.md", readme),
    ("docs/production-readiness.md", production),
):
    require(
        "docs/auditor-evidence-matrix.md" in content or "auditor-evidence-matrix.md" in content,
        f"{linked_doc} must link the auditor evidence matrix",
    )

for readme_phrase in (
    "compact context cards",
    "visible document/archive scope",
    "registered source count",
    "local rebuild posture",
):
    require(readme_phrase in readme, f"README missing document UI phrase: {readme_phrase}")

require(
    "auditor-evidence-matrix-check" in makefile,
    "Makefile must expose the auditor evidence matrix check",
)
require(
    "check_auditor_evidence_matrix.sh" in ci,
    "CI must run the auditor evidence matrix guard",
)
require(
    "Final release promotion still requires" in tracker,
    "process tracker must keep final release blockers visible",
)

print("Auditor evidence matrix OK: objective requirements map to gates and blockers.")
PY
