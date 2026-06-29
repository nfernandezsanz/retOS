from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_branding_assets.sh"
REQUIRED_FILES = (
    Path("README.md"),
    Path("docs/branding.md"),
    Path("docs/assets/retos-project-card.svg"),
    Path("frontend/public/retos-mark.svg"),
    Path("frontend/index.html"),
    Path("frontend/package.json"),
    Path("frontend/src/styles.css"),
    Path("frontend/src/App.tsx"),
    Path("frontend/e2e/app.spec.ts"),
    Path(".gitignore"),
    Path(".dockerignore"),
    Path(".github/workflows/ci.yml"),
)


def copy_minimal_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    for relative in REQUIRED_FILES:
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    return repo


def run_checker(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ["/bin/bash", str(CHECKER)],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        env=os.environ,
    )


def replace_text(path: Path, old: str, new: str) -> None:
    content = path.read_text(encoding="utf-8")
    assert old in content
    path.write_text(content.replace(old, new), encoding="utf-8")


def test_branding_assets_check_passes_for_current_contract(tmp_path: Path) -> None:
    repo = copy_minimal_repo(tmp_path)

    result = run_checker(repo)

    assert result.returncode == 0, result.stderr
    assert "Branding assets OK" in result.stdout


def test_branding_assets_check_fails_when_readme_loses_project_card(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(
        repo / "README.md",
        "![RetOS project card](docs/assets/retos-project-card.svg)",
        "RetOS project card",
    )

    result = run_checker(repo)

    assert result.returncode != 0
    assert "README missing brand/readiness phrase" in result.stderr


def test_branding_assets_check_fails_when_css_primary_color_drifts(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(
        repo / "frontend" / "src" / "styles.css",
        "--retos-primary: #2563eb",
        "--retos-primary: #7c3aed",
    )

    result = run_checker(repo)

    assert result.returncode != 0
    assert "frontend CSS missing brand token --retos-primary: #2563eb" in result.stderr


def test_branding_assets_check_fails_when_svg_loses_accessible_role(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(repo / "frontend" / "public" / "retos-mark.svg", 'role="img"', "")

    result = run_checker(repo)

    assert result.returncode != 0
    assert "mark SVG needs role=img" in result.stderr


def test_branding_assets_check_fails_when_favicon_is_removed(tmp_path: Path) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(repo / "frontend" / "index.html", 'rel="icon"', 'rel="shortcut"')

    result = run_checker(repo)

    assert result.returncode != 0
    assert "frontend must use mark favicon" in result.stderr


def test_branding_assets_check_fails_when_ci_drops_visual_audit_artifact(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(
        repo / ".github" / "workflows" / "ci.yml",
        "retos-visual-audit-${{ github.sha }}",
        "retos-ui-screenshots",
    )

    result = run_checker(repo)

    assert result.returncode != 0
    assert "CI must preserve visual audit evidence" in result.stderr
