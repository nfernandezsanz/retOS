.PHONY: help install test lint typecheck frontend-install frontend-test docker-build docker-up docker-down

help:
	@printf "RetOS development commands\n"
	@printf "  make install          Install backend dependencies\n"
	@printf "  make test             Run backend tests with coverage gate\n"
	@printf "  make lint             Run backend lint checks\n"
	@printf "  make typecheck        Run backend type checks\n"
	@printf "  make frontend-install Install frontend dependencies\n"
	@printf "  make frontend-test    Run frontend checks\n"
	@printf "  make docker-build     Build Docker images\n"
	@printf "  make docker-up        Start the full local stack\n"
	@printf "  make docker-down      Stop the local stack\n"

install:
	python3 -m pip install -r backend/requirements-dev.txt

test:
	cd backend && python3 -m pytest

lint:
	cd backend && python3 -m ruff check src tests

typecheck:
	cd backend && python3 -m mypy src

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
