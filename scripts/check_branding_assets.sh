#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
from __future__ import annotations

from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Branding assets failed: {message}")


paths = {
    "readme": Path("README.md"),
    "branding": Path("docs/branding.md"),
    "project_card": Path("docs/assets/retos-project-card.svg"),
    "mark": Path("frontend/public/retos-mark.svg"),
    "index": Path("frontend/index.html"),
    "package_json": Path("frontend/package.json"),
    "styles": Path("frontend/src/styles.css"),
    "app": Path("frontend/src/App.tsx"),
    "e2e": Path("frontend/e2e/app.spec.ts"),
    "gitignore": Path(".gitignore"),
    "dockerignore": Path(".dockerignore"),
    "ci": Path(".github/workflows/ci.yml"),
}

for name, path in paths.items():
    require(path.is_file() and path.stat().st_size > 0, f"missing or empty {name}: {path}")

readme = paths["readme"].read_text(encoding="utf-8")
branding = paths["branding"].read_text(encoding="utf-8")
project_card = paths["project_card"].read_text(encoding="utf-8")
mark = paths["mark"].read_text(encoding="utf-8")
index = paths["index"].read_text(encoding="utf-8")
package_json = paths["package_json"].read_text(encoding="utf-8")
styles = paths["styles"].read_text(encoding="utf-8")
app = paths["app"].read_text(encoding="utf-8")
e2e = paths["e2e"].read_text(encoding="utf-8")
gitignore = paths["gitignore"].read_text(encoding="utf-8")
dockerignore = paths["dockerignore"].read_text(encoding="utf-8")
ci = paths["ci"].read_text(encoding="utf-8")

for phrase in (
    "![RetOS project card](docs/assets/retos-project-card.svg)",
    "actions/workflows/ci.yml/badge.svg?branch=main",
    "actions/workflows/release.yml/badge.svg",
    "**Action pills**",
    "I want to try it locally",
    "I want to audit it before trusting it",
    "I want to develop with agents",
    "compact Overview plus hash-addressable Documents, Queries, Evals, Audit, and Admin",
    "section navigation, tooltip contract",
    "Branding assets and visual guidance",
    "docs/production-readiness.md",
):
    require(phrase in readme, f"README missing brand/readiness phrase: {phrase}")

for phrase in (
    "operational research console",
    "flat SaaS operational-dashboard pattern",
    "minimal and direct operational console",
    "dense, scan-friendly layouts",
    "compact Overview plus hash-addressable Documents",
    "Tooltips: navigation links and high-impact actions",
    "flat colors",
    "trust blue primary",
    "verification orange action",
    "Plus Jakarta Sans-compatible",
    "emoji icons",
    "color alone is never the signal",
    "frontend/public/retos-mark.svg",
    "docs/assets/retos-project-card.svg",
):
    require(phrase in branding, f"docs/branding.md missing guidance phrase: {phrase}")

brand_colors = {
    "--retos-ink": "#0f172a",
    "--retos-primary": "#2563eb",
    "--retos-action": "#f97316",
    "--retos-canvas": "#f8fafc",
    "--retos-surface": "#ffffff",
    "--retos-border": "#dbe3ef",
}
for token, value in brand_colors.items():
    require(f"{token}: {value}" in styles, f"frontend CSS missing brand token {token}: {value}")
    require(value in branding, f"docs/branding.md missing palette value {value}")

for svg_name, svg in (("project card", project_card), ("mark", mark)):
    require("<title" in svg and "<desc" in svg, f"{svg_name} SVG needs title and desc")
    require('role="img"' in svg, f"{svg_name} SVG needs role=img")

require('rel="icon"' in index and "/retos-mark.svg" in index, "frontend must use mark favicon")
require('meta name="theme-color" content="#0f172a"' in index, "frontend theme color must match ink")
require('<img src="/retos-mark.svg" alt="" aria-hidden="true" />' in app, "sidebar must use brand mark")

for phrase in (
    "keeps the RetOS brand system accessible and responsive",
    'emulateMedia({ reducedMotion: "reduce" })',
    "375, 768, 1024, 1440",
    "data-tooltip",
    "retos-mark.svg",
    "Hash-chained journals",
):
    require(phrase in e2e, f"Playwright brand smoke missing phrase: {phrase}")

require("@media (prefers-reduced-motion: reduce)" in styles, "CSS must respect reduced motion")
require("@media (max-width: 900px)" in styles, "CSS must define mobile responsive layout")
require("visual-audit" in package_json, "frontend package must expose a visual audit script")
for phrase in (
    "RETOS_VISUAL_AUDIT",
    "retos-console-desktop.png",
    "retos-console-mobile.png",
    "manifest.json",
    "sha256",
    "size_bytes",
    "viewport",
):
    require(phrase in e2e, f"Playwright visual audit missing phrase: {phrase}")
require(
    "make frontend-visual-audit" in readme
    and "frontend/visual-audit/manifest.json" in readme
    and "make visual-audit-check" in readme
    and "make frontend-visual-audit" in branding
    and "make visual-audit-check" in branding
    and "frontend/visual-audit/manifest.json" in branding,
    "README and branding guide must document the visual audit commands and manifest",
)
require(
    "workspaceSections" in app
    and "sectionFromHash" in app
    and 'aria-current={activeSection === section.id ? "page" : undefined}' in app
    and "section-switcher" in styles
    and "overview-actions" in styles
    and "[data-tooltip]::after" in styles,
    "frontend must keep section navigation, Overview actions, and tooltip styling aligned",
)
require("frontend/visual-audit/" in gitignore, ".gitignore must exclude visual audit PNGs")
require("frontend/visual-audit" in dockerignore, ".dockerignore must exclude visual audit PNGs")
require("npm run visual-audit" in ci, "CI must run the frontend visual audit")
for phrase in (
    "actions/upload-artifact@v4",
    "retos-visual-audit-${{ github.sha }}",
    "frontend/visual-audit/*.png",
    "frontend/visual-audit/manifest.json",
    "if-no-files-found: error",
):
    require(phrase in ci, f"CI must preserve visual audit evidence: {phrase}")

print("Branding assets OK: project image, mark, palette, docs, and UI smoke are aligned.")
PY
