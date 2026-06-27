.PHONY: help install format format-check test lint typecheck check frontend-install frontend-test docker-build docker-up docker-down

help:
	@printf "RetOS development commands\n"
	@printf "  make install          Install backend dependencies\n"
	@printf "  make format           Format backend code with Black\n"
	@printf "  make format-check     Check backend Black formatting\n"
	@printf "  make test             Run backend tests with coverage gate\n"
	@printf "  make lint             Run backend lint checks\n"
	@printf "  make typecheck        Run backend type checks\n"
	@printf "  make check            Run backend format/lint/typecheck/tests\n"
	@printf "  make frontend-install Install frontend dependencies\n"
	@printf "  make frontend-test    Run frontend checks\n"
	@printf "  make docker-build     Build Docker images\n"
	@printf "  make docker-up        Start the full local stack\n"
	@printf "  make docker-down      Stop the local stack\n"

install:
	python3 -m pip install -r backend/requirements-dev.txt

format:
	cd backend && python3 -m black src tests

format-check:
	cd backend && python3 -m black --check --diff src tests

test:
	cd backend && python3 -m pytest

lint:
	cd backend && python3 -m ruff check src tests

typecheck:
	cd backend && python3 -m mypy src

check: format-check lint typecheck test

frontend-install:
	cd frontend && npm install

frontend-test:
	cd frontend && npm run check

docker-build:
	docker compose build

docker-up:
	docker compose up --build

docker-down:
	docker compose down
