# Contributing

Thanks for contributing to RetOS.

## Development Setup

Requirements:

- Python 3.14
- Node.js 24 or newer
- Docker and Docker Compose

Install backend dependencies:

```bash
python3 -m pip install -r backend/requirements-dev.txt
```

Install frontend dependencies:

```bash
cd frontend
npm install
```

## Checks

Use the fast loop while developing:

```bash
make doctor
make format
make format-check
make lint
make typecheck
make test
make api-smoke
make frontend-test
make frontend-e2e
```

Use `make integration` when changing API routes, auth, SSE, frontend routing, job status, or anything users observe through the browser.

Before asking for review on a release-facing or auditor-facing change, run the local
acceptance gate:

```bash
make doctor
make local-acceptance
```

The doctor checks local prerequisites, safe defaults, Compose config, topology, and audit
tooling before heavier gates. The acceptance gate covers backend quality, API/browser
integration, frontend build, visual audit, Docker config, auditor handoff, and Docker
stack smoke without paid LLM providers.

## Security Rules

- Do not commit secrets.
- Do not add tests that call paid LLM providers by default.
- Do not log API keys, credentials, full document text, or raw uploads.
- Use package-level adapters for external services so tests can mock them cleanly.
- When a route or UI workflow changes, add or update an integration/API/browser smoke check.

## Commit Style

Use concise, imperative commit messages:

```text
Initialize Dockerized project scaffold
```
