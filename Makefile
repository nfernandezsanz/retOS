ROOT_DIR := $(CURDIR)
PYTHON ?= python3
BACKEND_PYTHON ?= $(if $(wildcard $(ROOT_DIR)/.venv/bin/python),$(ROOT_DIR)/.venv/bin/python,$(PYTHON))

.PHONY: help install format format-check test lint typecheck db-upgrade db-downgrade api-smoke eval-smoke eval-agent-multihop eval-fetch-dataset eval-ocr eval-ocr-benchmark eval-squad eval-hotpotqa eval-natural-questions check frontend-install frontend-test frontend-e2e integration docker-config docker-build docker-smoke release-check release-notes-check versioned-release-notes-check release-workflow-check image-size-check docker-up docker-down

help:
	@printf "RetOS development commands\n"
	@printf "  make install          Install backend dependencies\n"
	@printf "  make format           Format backend code with Black\n"
	@printf "  make format-check     Check backend Black formatting\n"
	@printf "  make test             Run backend tests with coverage gate\n"
	@printf "  make lint             Run backend lint checks\n"
	@printf "  make typecheck        Run backend type checks\n"
	@printf "  make db-upgrade       Apply Alembic migrations\n"
	@printf "  make db-downgrade     Roll back the latest Alembic migration\n"
	@printf "  make api-smoke        Start the API and hit real HTTP endpoints\n"
	@printf "  make eval-smoke       Run deterministic local retrieval/citation evals\n"
	@printf "  make eval-agent-multihop Run deterministic agent multi-hop evals\n"
	@printf "  make eval-fetch-dataset Fetch an opt-in public eval dataset sample with PROFILE=...\n"
	@printf "  make eval-ocr         Run opt-in local OCR quality evals\n"
	@printf "  make eval-ocr-benchmark Run OCR benchmark evals with OCR_PATH=...\n"
	@printf "  make eval-squad       Run opt-in SQuAD v2 evals with SQUAD_PATH=...\n"
	@printf "  make eval-hotpotqa    Run opt-in HotpotQA evals with HOTPOTQA_PATH=...\n"
	@printf "  make eval-natural-questions Run opt-in Natural Questions evals with NQ_PATH=...\n"
	@printf "  make check            Run backend format/lint/typecheck/tests\n"
	@printf "  make frontend-install Install frontend dependencies\n"
	@printf "  make frontend-test    Run frontend checks\n"
	@printf "  make frontend-e2e     Run browser smoke tests against the UI\n"
	@printf "  make integration      Run API and frontend smoke tests\n"
	@printf "  make docker-config    Validate Docker Compose configuration\n"
	@printf "  make docker-build     Build Docker images\n"
	@printf "  make docker-smoke     Build and smoke the Docker stack\n"
	@printf "  make release-check    Validate release docs, defaults, and Docker topology\n"
	@printf "  make release-notes-check Validate changelog and release note guidance\n"
	@printf "  make versioned-release-notes-check Validate versioned release note artifacts\n"
	@printf "  make release-workflow-check Validate GHCR publishing and signing workflow\n"
	@printf "  make image-size-check Validate built app image size budgets\n"
	@printf "  make docker-up        Start the full local stack\n"
	@printf "  make docker-down      Stop the local stack\n"

install:
	$(PYTHON) -m pip install -r backend/requirements-dev.txt

format:
	cd backend && "$(BACKEND_PYTHON)" -m black src tests scripts

format-check:
	cd backend && "$(BACKEND_PYTHON)" -m black --check --diff src tests scripts

test:
	cd backend && "$(BACKEND_PYTHON)" -m pytest

lint:
	cd backend && "$(BACKEND_PYTHON)" -m ruff check src tests scripts

typecheck:
	cd backend && "$(BACKEND_PYTHON)" -m mypy src

db-upgrade:
	cd backend && "$(BACKEND_PYTHON)" -m alembic upgrade head

db-downgrade:
	cd backend && "$(BACKEND_PYTHON)" -m alembic downgrade -1

api-smoke:
	cd backend && PYTHON="$(BACKEND_PYTHON)" scripts/run_api_smoke.sh

eval-smoke:
	cd backend && PYTHONPATH=src "$(BACKEND_PYTHON)" scripts/run_eval_smoke.py --format markdown

eval-agent-multihop:
	cd backend && PYTHONPATH=src "$(BACKEND_PYTHON)" scripts/run_eval_smoke.py --suite agent-multihop --format markdown $(if $(REPORT_DIR),--report-dir "$(REPORT_DIR)",) $(if $(REPORT_STEM),--report-stem "$(REPORT_STEM)",)

eval-fetch-dataset:
ifndef PROFILE
	$(error PROFILE is required, for example make eval-fetch-dataset PROFILE=squad-dev-v2)
endif
	cd backend && PYTHONPATH=src "$(BACKEND_PYTHON)" scripts/fetch_eval_dataset.py "$(PROFILE)" --output-dir "../evals/datasets" --max-records "$(or $(MAX_RECORDS),100)" $(if $(FORCE),--force,) $(if $(SOURCE_PATH),--source-path "$(abspath $(SOURCE_PATH))",)

eval-ocr:
	cd backend && PYTHONPATH=src "$(BACKEND_PYTHON)" scripts/run_eval_smoke.py --suite ocr-smoke --format markdown $(if $(REPORT_DIR),--report-dir "$(REPORT_DIR)",) $(if $(REPORT_STEM),--report-stem "$(REPORT_STEM)",)

eval-ocr-benchmark:
ifndef OCR_PATH
	$(error OCR_PATH is required, for example make eval-ocr-benchmark OCR_PATH=evals/datasets/ocr-benchmark/manifest.json)
endif
	cd backend && PYTHONPATH=src "$(BACKEND_PYTHON)" scripts/run_eval_smoke.py --suite ocr-benchmark --dataset-path "$(OCR_PATH)" --dataset-format "$(or $(OCR_FORMAT),manifest)" --max-cases "$(or $(MAX_CASES),50)" --format markdown $(if $(REPORT_DIR),--report-dir "$(REPORT_DIR)",) $(if $(REPORT_STEM),--report-stem "$(REPORT_STEM)",)

eval-squad:
ifndef SQUAD_PATH
	$(error SQUAD_PATH is required, for example make eval-squad SQUAD_PATH=evals/datasets/dev-v2.0.json)
endif
	cd backend && PYTHONPATH=src "$(BACKEND_PYTHON)" scripts/run_eval_smoke.py --suite squad --dataset-path "$(SQUAD_PATH)" --max-cases "$(or $(MAX_CASES),50)" --format markdown $(if $(REPORT_DIR),--report-dir "$(REPORT_DIR)",) $(if $(REPORT_STEM),--report-stem "$(REPORT_STEM)",)

eval-hotpotqa:
ifndef HOTPOTQA_PATH
	$(error HOTPOTQA_PATH is required, for example make eval-hotpotqa HOTPOTQA_PATH=evals/datasets/hotpot_dev_distractor_v1.json)
endif
	cd backend && PYTHONPATH=src "$(BACKEND_PYTHON)" scripts/run_eval_smoke.py --suite hotpotqa --dataset-path "$(HOTPOTQA_PATH)" --max-cases "$(or $(MAX_CASES),50)" --format markdown $(if $(REPORT_DIR),--report-dir "$(REPORT_DIR)",) $(if $(REPORT_STEM),--report-stem "$(REPORT_STEM)",)

eval-natural-questions:
ifndef NQ_PATH
	$(error NQ_PATH is required, for example make eval-natural-questions NQ_PATH=evals/datasets/nq-dev-sample.jsonl)
endif
	cd backend && PYTHONPATH=src "$(BACKEND_PYTHON)" scripts/run_eval_smoke.py --suite natural-questions --dataset-path "$(NQ_PATH)" --max-cases "$(or $(MAX_CASES),50)" --format markdown $(if $(REPORT_DIR),--report-dir "$(REPORT_DIR)",) $(if $(REPORT_STEM),--report-stem "$(REPORT_STEM)",)

check: format-check lint typecheck test eval-smoke eval-agent-multihop

frontend-install:
	cd frontend && npm install

frontend-test:
	cd frontend && npm run check

frontend-e2e:
	cd frontend && npm run e2e

integration: api-smoke frontend-e2e

docker-config:
	docker compose --env-file .env.example config
	scripts/check_docker_topology.sh

docker-build:
	docker compose build api web

docker-smoke:
	scripts/run_docker_smoke.sh

release-check:
	scripts/check_release_readiness.sh

release-notes-check:
	scripts/check_release_notes.sh

versioned-release-notes-check:
	scripts/check_versioned_release_notes.sh

release-workflow-check:
	scripts/check_release_workflow.sh

image-size-check:
	RETOS_REQUIRE_BUILT_IMAGES=1 scripts/check_image_size.sh

docker-up:
	docker compose up --build

docker-down:
	docker compose down
