# Visual Review Evidence Template

Use this template for the human visual acceptance pass after `make frontend-visual-audit`
and `make visual-audit-check` pass. Keep the completed copy with the production
promotion evidence or the versioned release note for the target environment.

## Candidate

| Field | Value |
| --- | --- |
| Release version | `<version>` |
| Commit SHA | `<full-sha>` |
| GitHub Actions run | `<url>` |
| Target environment | `<environment>` |
| Reviewer | `<name>` |
| Review date | `<YYYY-MM-DD>` |

## Machine Evidence

Paste or link the output for each gate:

- `make frontend-test`
- `make frontend-e2e`
- `make frontend-visual-audit`
- `make visual-audit-check`
- `make brand-check`
- `make readme-check`

## Screenshot Evidence

| Field | Value |
| --- | --- |
| Visual audit manifest | `frontend/visual-audit/manifest.json` |
| Desktop screenshot | `frontend/visual-audit/retos-console-desktop.png` |
| Desktop viewport | `1440x900` |
| Desktop SHA-256 | `<sha256>` |
| Mobile screenshot | `frontend/visual-audit/retos-console-mobile.png` |
| Mobile viewport | `390x844` |
| Mobile SHA-256 | `<sha256>` |
| Remote artifact | `retos-visual-audit-<commit>` |

## Review Scope

- Overview first screen reviewed:
- Documents workflow reviewed:
- Queries workflow reviewed:
- Evals workflow reviewed:
- Audit workflow reviewed:
- Admin workflow reviewed:
- Tooltip hover/focus behavior reviewed:
- Keyboard focus and skip link reviewed:
- Mobile overflow reviewed:
- Desktop overflow reviewed:
- Reduced motion reviewed:
- Brand mark, palette, and project card reviewed:

## Findings

- Visual defects found:
- Accessibility concerns found:
- Responsiveness concerns found:
- Accepted visual risks:
- Follow-up issue links:

## Decision

- Visual review decision:
- Reviewer sign-off:
- Promotion impact:
