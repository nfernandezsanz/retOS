# RetOS Branding

RetOS should feel like an operational research console: calm, auditable, local-first, and ready for repeated technical use.

## Visual Principles

- Use dense, scan-friendly layouts for work surfaces.
- Prefer flat colors, crisp borders, and stable hover/focus states.
- Avoid decorative gradients, oversized marketing sections, and purely atmospheric imagery.
- Keep every status readable with text plus color; color alone is never the signal.

## Design-System Decision

RetOS follows a flat SaaS operational-dashboard pattern: direct navigation, compact
information density, explicit status text, Lucide icons, and restrained color accents.
This is intentional for a repeated-use audit console; the first screen should expose the
working system instead of a marketing landing page.

The brand contract aligns with the selected design direction:

- Pattern: minimal and direct operational console.
- Style: flat design with crisp borders, no decorative gradients, and no heavy shadows.
- Colors: trust blue primary (`#2563eb`), verification orange action (`#f97316`),
  quiet canvas (`#f8fafc`), and high-contrast ink (`#0f172a`).
- Typography: system UI fonts for offline Docker reliability, with a Plus Jakarta
  Sans-compatible direction for future packaged font assets.
- Anti-patterns: cluttered onboarding, hidden operational state, color-only status,
  emoji icons, and hero/marketing layouts that delay the work surface.

## Palette

| Role | Hex | Use |
| --- | --- | --- |
| Ink | `#0f172a` | Sidebar, primary text, brand ground |
| Surface | `#ffffff` | Panels and repeated rows |
| Canvas | `#f8fafc` | Page background and quiet grouped areas |
| Border | `#dbe3ef` | Panel, row, and input borders |
| Primary | `#2563eb` | Navigation focus, links, selected operational state |
| Primary Soft | `#eff6ff` | Informational status backgrounds |
| Action | `#f97316` | Primary calls to action and verification accent |
| Success | `#166534` | Passing checks and healthy local state |
| Warning | `#9a3412` | Attention states and archived records |
| Danger | `#991b1b` | Destructive or failed states |

## Typography

The app uses system UI fonts by default for Docker/offline reliability. The intended brand direction is Plus Jakarta Sans-compatible: geometric, readable, and professional. Avoid decorative typefaces.

## UI Contract

- Primary product surface: React operational console, not a marketing landing page.
- Pattern: dense, scan-friendly SaaS dashboard with flat color, crisp borders, and
  stable 8px-radius controls.
- Icons: Lucide SVG icons only; no emoji-as-icon UI.
- Accessibility: visible focus rings, skip link, text labels beside color states,
  44px primary controls, and `prefers-reduced-motion` support.
- Responsive behavior: single-column workspace below 900px with no horizontal page
  overflow at 375px, 768px, 1024px, or 1440px.

## Latest Visual Audit

- Desktop 1440x900: sidebar brand, first-viewport heading, operating-posture band,
  metrics, domain management, query workspace, and primary action render without
  overlap or horizontal overflow.
- Mobile 390x844: navigation wraps into a two-row grid, the heading remains readable,
  the primary action fills the content width, and the page reports no horizontal
  overflow.
- Automated coverage: `frontend/e2e/app.spec.ts` verifies brand tokens, favicon,
  responsive breakpoints, skip-link focus, reduced motion, mobile provider controls,
  and the full operational console flow.
- Reproducible screenshots: run `make frontend-visual-audit` to write ignored local
  desktop and mobile PNGs under `frontend/visual-audit/` for human design review.
- CI evidence: the frontend workflow uploads those PNGs as a
  `retos-visual-audit-<commit>` artifact so remote reviewers can download the
  exact desktop and mobile screenshots produced by the run.

## Assets

- Frontend mark: `frontend/public/retos-mark.svg`
- Project card: `docs/assets/retos-project-card.svg`

The mark represents a document ledger, a verification path, and a local runtime surface. It should be used as the favicon, sidebar brand mark, and compact project identity image.
