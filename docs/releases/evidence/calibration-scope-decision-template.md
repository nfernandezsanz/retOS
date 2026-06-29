# Calibration Scope Decision Evidence Template

Use this template when a release candidate relies on bounded public calibration slices or
when broader public-slice trend evidence is attached. Keep the completed copy with the
production promotion evidence for the release candidate.

## Candidate

| Field | Value |
| --- | --- |
| Release version | `<version>` |
| Immutable release tag | `v<version>` |
| Commit SHA | `<full-sha>` |
| Target environment | `<environment>` |
| Reviewer | `<name>` |
| Review date | `<YYYY-MM-DD>` |

## Versioned Evidence

- Calibration evidence file:
- Calibration trend evidence file:
- `make eval-calibration-gate` output:
- `make eval-calibration-trend-gate` output:
- Baseline record cap:
- Candidate record cap:
- Baseline case cap:
- Candidate case cap:
- Required targets reviewed:
- Metric gates reviewed:

## Pilot Scope Acceptance

- Pilot scope accepted:
- Accepted scope limit:
- Pilot user group:
- Pilot corpus boundary:
- Pilot duration:
- Manual review cadence:
- Stop criteria:
- Expansion trigger:
- Promotion owner:
- Follow-up issue:

## Broader Trend Evidence

- Broader trend evidence attached:
- Larger baseline record cap:
- Larger candidate record cap:
- Larger baseline case cap:
- Larger candidate case cap:
- Additional dataset targets:
- Regression tolerance:
- Trend decision:
- Evidence artifact links:
- Follow-up issue:

## Risk Decision

- Calibration decision:
- Accepted risks:
- Required follow-up issues:
- Promotion impact:
