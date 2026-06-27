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

Run before opening a pull request:

```bash
make lint
make typecheck
make test
make frontend-test
```

## Security Rules

- Do not commit secrets.
- Do not add tests that call paid LLM providers by default.
- Do not log API keys, credentials, full document text, or raw uploads.
- Use package-level adapters for external services so tests can mock them cleanly.

## Commit Style

Use concise, imperative commit messages:

```text
Initialize Dockerized project scaffold
```
