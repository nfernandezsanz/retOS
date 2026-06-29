ROOT_DIR := $(CURDIR)
PYTHON ?= python3
BACKEND_PYTHON ?= $(if $(wildcard $(ROOT_DIR)/.venv/bin/python),$(ROOT_DIR)/.venv/bin/python,$(PYTHON))
BRANCH_COVERAGE_MIN ?= 90.65
AUDIT_MANIFEST_OUTPUT ?= evals/reports/audit-manifest.json
AUDIT_HANDOFF_REPORT_OUTPUT ?= evals/reports/audit-handoff.md
AUDIT_BUNDLE_OUTPUT ?= evals/reports/retos-audit-handoff.tar.gz
AUDIT_MANIFEST_SKIP_CI ?= false

.PHONY: help doctor env-security-check seed-demo docker-seed-demo install format format-check test lint typecheck dependency-audit security-policy-check ignore-hygiene-check operations-runbook-check backup-restore-drill-check promotion-template-check auditor-evidence-matrix-check auditor-static-check auditor-handoff-check audit-manifest audit-manifest-check audit-handoff-report audit-handoff-report-check audit-bundle audit-bundle-check audit-export-check visual-audit-check db-upgrade db-downgrade api-smoke eval-smoke eval-agent-multihop eval-fetch-dataset eval-calibration eval-calibration-evidence eval-calibration-gate eval-calibration-trend-gate eval-calibration-compare eval-ocr eval-ocr-benchmark eval-squad eval-hotpotqa eval-hotpotqa-agent eval-natural-questions check local-acceptance frontend-install frontend-test frontend-e2e frontend-visual-audit integration docker-config docker-build docker-runtime-image-check docker-smoke release-check audit-pack-check production-preflight brand-check ci-status-check release-notes-check versioned-release-notes-check release-workflow-check release-evidence-check image-size-check docker-up docker-down

help:
	@printf "RetOS development commands\n"
	@printf "  make doctor           Check local prerequisites, safe defaults, Compose config, and audit tooling\n"
	@printf "  make env-security-check Validate active .env security posture without starting services\n"
	@printf "  make seed-demo        Seed an auditable local demo corpus and rebuild search\n"
	@printf "  make docker-seed-demo Seed the running Docker stack through the API container\n"
	@printf "  make install          Install backend dependencies\n"
	@printf "  make format           Format backend code with Black\n"
	@printf "  make format-check     Check backend Black formatting\n"
	@printf "  make test             Run backend tests with coverage gate\n"
	@printf "  make lint             Run backend lint checks\n"
	@printf "  make typecheck        Run backend type checks\n"
	@printf "  make dependency-audit Audit Python and Node dependency advisories\n"
	@printf "  make security-policy-check Validate security policy and human review links\n"
	@printf "  make ignore-hygiene-check Validate Git and Docker ignore rules\n"
	@printf "  make operations-runbook-check Validate backup, restore, rollback, and audit-export runbooks\n"
	@printf "  make backup-restore-drill-check Validate backup/restore drill evidence template\n"
	@printf "  make promotion-template-check Validate human promotion evidence template contract\n"
	@printf "  make auditor-evidence-matrix-check Validate objective-to-evidence traceability\n"
	@printf "  make auditor-static-check Run non-destructive auditor documentation/release/security gates\n"
	@printf "  make auditor-handoff-check Run static gates and export manifest, checklist report, and bundle\n"
	@printf "  make audit-manifest   Export a JSON manifest for human production audit handoff\n"
	@printf "  make audit-manifest-check Validate audit manifest schema offline\n"
	@printf "  make audit-handoff-report Export a human-readable Markdown audit handoff\n"
	@printf "  make audit-handoff-report-check Validate the generated handoff report shape\n"
	@printf "  make audit-bundle    Export a tar.gz auditor handoff bundle with checksum\n"
	@printf "  make audit-bundle-check Validate the generated auditor bundle shape\n"
	@printf "  make audit-export-check Validate /audit/export JSON with EXPORT=path, or self-test verifier\n"
	@printf "  make visual-audit-check Validate local visual-audit manifest and screenshot hashes\n"
	@printf "  make db-upgrade       Apply Alembic migrations\n"
	@printf "  make db-downgrade     Roll back the latest Alembic migration\n"
	@printf "  make api-smoke        Start the API and hit real HTTP endpoints\n"
	@printf "  make eval-smoke       Run deterministic local retrieval/citation evals\n"
	@printf "  make eval-agent-multihop Run deterministic agent multi-hop evals\n"
	@printf "  make eval-fetch-dataset Fetch an opt-in public eval dataset sample with PROFILE=...\n"
	@printf "  make eval-calibration  Fetch bounded public samples and run real-dataset calibration\n"
	@printf "  make eval-calibration-evidence Export path-safe Markdown evidence from a calibration manifest\n"
	@printf "  make eval-calibration-gate Validate versioned calibration evidence for local promotion review\n"
	@printf "  make eval-calibration-trend-gate Validate versioned calibration trend evidence\n"
	@printf "  make eval-calibration-compare Compare two calibration manifests for trend evidence\n"
	@printf "  make eval-ocr         Run opt-in local OCR quality evals\n"
	@printf "  make eval-ocr-benchmark Run OCR benchmark evals with OCR_PATH=...\n"
	@printf "  make eval-squad       Run opt-in SQuAD v2 evals with SQUAD_PATH=...\n"
	@printf "  make eval-hotpotqa    Run opt-in HotpotQA evals with HOTPOTQA_PATH=...\n"
	@printf "  make eval-hotpotqa-agent Run HotpotQA supporting facts through the agent audit harness with HOTPOTQA_PATH=...\n"
	@printf "  make eval-natural-questions Run opt-in Natural Questions evals with NQ_PATH=...\n"
	@printf "  make check            Run backend format/lint/typecheck/tests\n"
	@printf "  make local-acceptance Run the local pre-audit acceptance gate\n"
	@printf "  make frontend-install Install frontend dependencies\n"
	@printf "  make frontend-test    Run frontend checks\n"
	@printf "  make frontend-e2e     Run browser smoke tests against the UI\n"
	@printf "  make frontend-visual-audit Generate local desktop/mobile UI audit screenshots\n"
	@printf "  make integration      Run API and frontend smoke tests\n"
	@printf "  make docker-config    Validate Docker Compose configuration\n"
	@printf "  make docker-build     Build Docker images\n"
	@printf "  make docker-runtime-image-check Validate running backend roles share one image ID\n"
	@printf "  make docker-smoke     Build and smoke the Docker stack\n"
	@printf "  make release-check    Validate release docs, defaults, and Docker topology\n"
	@printf "  make audit-pack-check Validate production readiness audit evidence\n"
	@printf "  make production-preflight Validate local preflight evidence and external release blockers\n"
	@printf "  make brand-check      Validate project branding assets and UI brand smoke coverage\n"
	@printf "  make ci-status-check  Validate GitHub Actions is green for current HEAD\n"
	@printf "  make release-notes-check Validate changelog and release note guidance\n"
	@printf "  make versioned-release-notes-check Validate versioned release note artifacts\n"
	@printf "  make release-workflow-check Validate GHCR publishing, signing, and verification workflow\n"
	@printf "  make release-evidence-check Verify published GHCR digests with Cosign\n"
	@printf "  make image-size-check Validate built app image size budgets\n"
	@printf "  make docker-up        Start the full local stack\n"
	@printf "  make docker-down      Stop the local stack\n"

doctor:
	"$(BACKEND_PYTHON)" scripts/check_local_doctor.py

env-security-check:
	"$(BACKEND_PYTHON)" scripts/check_env_security.py

seed-demo:
	cd backend && PYTHONPATH=src "$(BACKEND_PYTHON)" scripts/seed_demo.py $(SEED_DEMO_ARGS)

docker-seed-demo:
	docker compose exec api python /app/backend/scripts/seed_demo.py $(SEED_DEMO_ARGS)

install:
	$(PYTHON) -m pip install -r backend/requirements-dev.txt

format:
	cd backend && "$(BACKEND_PYTHON)" -m black src tests scripts

format-check:
	cd backend && "$(BACKEND_PYTHON)" -m black --check --diff src tests scripts

test:
	cd backend && "$(BACKEND_PYTHON)" -m pytest
	cd backend && "$(BACKEND_PYTHON)" scripts/check_branch_coverage.py --fail-under "$(BRANCH_COVERAGE_MIN)"

lint:
	cd backend && "$(BACKEND_PYTHON)" -m ruff check src tests scripts

typecheck:
	cd backend && "$(BACKEND_PYTHON)" -m mypy src

dependency-audit:
	BACKEND_PYTHON="$(BACKEND_PYTHON)" scripts/check_dependency_audit.sh

security-policy-check:
	scripts/check_security_policy.sh

ignore-hygiene-check:
	scripts/check_ignore_hygiene.sh

operations-runbook-check:
	scripts/check_operations_runbook.sh

backup-restore-drill-check:
	$(PYTHON) scripts/check_backup_restore_drill.py $(if $(TEMPLATE),--template "$(abspath $(TEMPLATE))",)

promotion-template-check:
	$(PYTHON) scripts/check_promotion_template.py $(if $(TEMPLATE),--template "$(abspath $(TEMPLATE))",)

auditor-evidence-matrix-check:
	scripts/check_auditor_evidence_matrix.sh

auditor-static-check: dependency-audit security-policy-check env-security-check ignore-hygiene-check operations-runbook-check backup-restore-drill-check promotion-template-check auditor-evidence-matrix-check brand-check visual-audit-check release-workflow-check release-notes-check versioned-release-notes-check eval-calibration-gate eval-calibration-trend-gate release-check production-preflight audit-pack-check audit-manifest-check audit-handoff-report-check audit-bundle-check

auditor-handoff-check: auditor-static-check
	$(MAKE) audit-manifest OUTPUT="$(AUDIT_MANIFEST_OUTPUT)" AUDIT_MANIFEST_SKIP_CI=true
	$(MAKE) audit-handoff-report MANIFEST="$(AUDIT_MANIFEST_OUTPUT)" OUTPUT="$(AUDIT_HANDOFF_REPORT_OUTPUT)"
	$(MAKE) audit-bundle OUTPUT="$(AUDIT_BUNDLE_OUTPUT)" AUDIT_MANIFEST_SKIP_CI=true
	@printf "Auditor handoff OK: local static gates, offline audit manifest, Markdown report, and bundle are ready at %s, %s, and %s\n" "$(AUDIT_MANIFEST_OUTPUT)" "$(AUDIT_HANDOFF_REPORT_OUTPUT)" "$(AUDIT_BUNDLE_OUTPUT)"

audit-manifest:
	$(PYTHON) scripts/export_audit_manifest.py $(if $(filter true,$(AUDIT_MANIFEST_SKIP_CI)),--skip-ci-lookup,) $(if $(OUTPUT),--output "$(abspath $(OUTPUT))",)

audit-manifest-check:
	$(PYTHON) scripts/check_audit_manifest.py

audit-handoff-report:
	$(PYTHON) scripts/export_audit_handoff_report.py --manifest "$(abspath $(or $(MANIFEST),$(AUDIT_MANIFEST_OUTPUT)))" $(if $(OUTPUT),--output "$(abspath $(OUTPUT))",)

audit-handoff-report-check:
	$(PYTHON) scripts/check_audit_handoff_report.py

audit-bundle:
	$(PYTHON) scripts/export_audit_bundle.py $(if $(filter true,$(AUDIT_MANIFEST_SKIP_CI)),--skip-ci-lookup,) $(if $(OUTPUT),--output "$(abspath $(OUTPUT))",)

audit-bundle-check:
	$(PYTHON) scripts/check_audit_bundle.py

audit-export-check:
	$(PYTHON) scripts/check_audit_export.py $(if $(EXPORT),--export "$(abspath $(EXPORT))",--self-test)

visual-audit-check:
	$(PYTHON) scripts/check_visual_audit.py $(if $(MANIFEST),--manifest "$(abspath $(MANIFEST))",)

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
	cd backend && PYTHONPATH=src "$(BACKEND_PYTHON)" scripts/fetch_eval_dataset.py "$(PROFILE)" --output-dir "../evals/datasets" --max-records "$(or $(MAX_RECORDS),100)" --download-timeout "$(or $(DOWNLOAD_TIMEOUT),60)" --download-retries "$(or $(DOWNLOAD_RETRIES),2)" $(if $(FORCE),--force,) $(if $(SOURCE_PATH),--source-path "$(abspath $(SOURCE_PATH))",)

eval-calibration:
	cd backend && PYTHONPATH=src:./scripts "$(BACKEND_PYTHON)" scripts/run_eval_calibration.py --dataset-dir "../evals/datasets" --report-dir "../evals/reports/calibration" --max-records "$(or $(MAX_RECORDS),100)" --download-timeout "$(or $(DOWNLOAD_TIMEOUT),60)" --download-retries "$(or $(DOWNLOAD_RETRIES),2)" $(if $(MAX_CASES),--max-cases "$(MAX_CASES)",) $(if $(FORCE),--force-datasets,) $(if $(TARGET),--target "$(TARGET)",) $(foreach gate,$(METRIC_GATES),--metric-gate "$(gate)")

eval-calibration-evidence:
	cd backend && "$(BACKEND_PYTHON)" scripts/export_eval_calibration_evidence.py --manifest "$(abspath $(or $(MANIFEST),evals/reports/calibration/manifest.json))" $(if $(OUTPUT),--output "$(abspath $(OUTPUT))",) $(if $(TITLE),--title "$(TITLE)",) $(if $(COMMAND),--command "$(COMMAND)",) $(if $(ALLOW_FAILED),--allow-failed,)

eval-calibration-gate:
	"$(BACKEND_PYTHON)" scripts/check_eval_calibration_evidence.py $(if $(EVIDENCE),--evidence "$(abspath $(EVIDENCE))",) $(if $(MIN_RECORDS),--min-records "$(MIN_RECORDS)",) $(if $(MIN_CASES),--min-cases "$(MIN_CASES)",) $(foreach target,$(TARGETS),--target "$(target)") $(foreach gate,$(REQUIRED_GATES),--required-gate "$(gate)")

eval-calibration-trend-gate:
	"$(BACKEND_PYTHON)" scripts/check_eval_calibration_trend.py $(if $(EVIDENCE),--evidence "$(abspath $(EVIDENCE))",) $(if $(MIN_BASELINE_RECORDS),--min-baseline-records "$(MIN_BASELINE_RECORDS)",) $(if $(MIN_CANDIDATE_RECORDS),--min-candidate-records "$(MIN_CANDIDATE_RECORDS)",) $(if $(MIN_BASELINE_CASES),--min-baseline-cases "$(MIN_BASELINE_CASES)",) $(if $(MIN_CANDIDATE_CASES),--min-candidate-cases "$(MIN_CANDIDATE_CASES)",) $(if $(MIN_RECORD_DELTA),--min-record-delta "$(MIN_RECORD_DELTA)",) $(if $(MIN_CASE_DELTA),--min-case-delta "$(MIN_CASE_DELTA)",) $(if $(MAX_REGRESSION),--max-regression "$(MAX_REGRESSION)",) $(foreach target,$(TARGETS),--target "$(target)")

eval-calibration-compare:
	@test -n "$(BASELINE)" || (echo "BASELINE is required" >&2; exit 2)
	@test -n "$(CANDIDATE)" || (echo "CANDIDATE is required" >&2; exit 2)
	cd backend && "$(BACKEND_PYTHON)" scripts/compare_eval_calibration.py --baseline "$(abspath $(BASELINE))" --candidate "$(abspath $(CANDIDATE))" --max-regression "$(or $(MAX_REGRESSION),0)" $(if $(OUTPUT),--output "$(abspath $(OUTPUT))",) $(if $(TITLE),--title "$(TITLE)",)

eval-ocr:
	cd backend && PYTHONPATH=src "$(BACKEND_PYTHON)" scripts/run_eval_smoke.py --suite ocr-smoke --format markdown $(if $(REPORT_DIR),--report-dir "$(REPORT_DIR)",) $(if $(REPORT_STEM),--report-stem "$(REPORT_STEM)",)

eval-ocr-benchmark:
ifndef OCR_PATH
	$(error OCR_PATH is required, for example make eval-ocr-benchmark OCR_PATH=evals/datasets/ocr-benchmark/manifest.json)
endif
	cd backend && PYTHONPATH=src "$(BACKEND_PYTHON)" scripts/run_eval_smoke.py --suite ocr-benchmark --dataset-path "$(abspath $(OCR_PATH))" --dataset-format "$(or $(OCR_FORMAT),manifest)" --max-cases "$(or $(MAX_CASES),50)" --format markdown $(if $(REPORT_DIR),--report-dir "$(abspath $(REPORT_DIR))",) $(if $(REPORT_STEM),--report-stem "$(REPORT_STEM)",)

eval-squad:
ifndef SQUAD_PATH
	$(error SQUAD_PATH is required, for example make eval-squad SQUAD_PATH=evals/datasets/dev-v2.0.json)
endif
	cd backend && PYTHONPATH=src "$(BACKEND_PYTHON)" scripts/run_eval_smoke.py --suite squad --dataset-path "$(abspath $(SQUAD_PATH))" --max-cases "$(or $(MAX_CASES),50)" --format markdown $(if $(REPORT_DIR),--report-dir "$(abspath $(REPORT_DIR))",) $(if $(REPORT_STEM),--report-stem "$(REPORT_STEM)",)

eval-hotpotqa:
ifndef HOTPOTQA_PATH
	$(error HOTPOTQA_PATH is required, for example make eval-hotpotqa HOTPOTQA_PATH=evals/datasets/hotpot_dev_distractor_v1.json)
endif
	cd backend && PYTHONPATH=src "$(BACKEND_PYTHON)" scripts/run_eval_smoke.py --suite hotpotqa --dataset-path "$(abspath $(HOTPOTQA_PATH))" --max-cases "$(or $(MAX_CASES),50)" --format markdown $(if $(REPORT_DIR),--report-dir "$(abspath $(REPORT_DIR))",) $(if $(REPORT_STEM),--report-stem "$(REPORT_STEM)",)

eval-hotpotqa-agent:
ifndef HOTPOTQA_PATH
	$(error HOTPOTQA_PATH is required, for example make eval-hotpotqa-agent HOTPOTQA_PATH=evals/datasets/hotpot_dev_distractor_v1.json)
endif
	cd backend && PYTHONPATH=src "$(BACKEND_PYTHON)" scripts/run_eval_smoke.py --suite hotpotqa-agent --dataset-path "$(abspath $(HOTPOTQA_PATH))" --max-cases "$(or $(MAX_CASES),50)" --format markdown $(if $(REPORT_DIR),--report-dir "$(abspath $(REPORT_DIR))",) $(if $(REPORT_STEM),--report-stem "$(REPORT_STEM)",)

eval-natural-questions:
ifndef NQ_PATH
	$(error NQ_PATH is required, for example make eval-natural-questions NQ_PATH=evals/datasets/nq-dev-sample.jsonl)
endif
	cd backend && PYTHONPATH=src "$(BACKEND_PYTHON)" scripts/run_eval_smoke.py --suite natural-questions --dataset-path "$(abspath $(NQ_PATH))" --max-cases "$(or $(MAX_CASES),50)" --format markdown $(if $(REPORT_DIR),--report-dir "$(abspath $(REPORT_DIR))",) $(if $(REPORT_STEM),--report-stem "$(REPORT_STEM)",)

check: format-check lint typecheck test eval-smoke eval-agent-multihop

local-acceptance: doctor check integration frontend-test frontend-visual-audit docker-config auditor-handoff-check docker-smoke
	@printf "Local acceptance OK: backend, API, frontend, visual audit, Docker config, auditor handoff, and Docker smoke passed.\n"

frontend-install:
	cd frontend && npm install

frontend-test:
	cd frontend && npm run check

frontend-e2e:
	cd frontend && npm run e2e

frontend-visual-audit:
	cd frontend && npm run visual-audit

integration: api-smoke frontend-e2e

docker-config:
	docker compose --env-file .env.example config
	scripts/check_docker_topology.sh

docker-build:
	docker compose build api web

docker-runtime-image-check:
	scripts/check_backend_runtime_image.sh

docker-smoke:
	scripts/run_docker_smoke.sh

release-check:
	scripts/check_release_readiness.sh

audit-pack-check:
	scripts/check_audit_pack.sh

production-preflight:
	scripts/check_production_preflight.sh

brand-check:
	scripts/check_branding_assets.sh

ci-status-check:
	scripts/check_ci_status.sh

release-notes-check:
	scripts/check_release_notes.sh

versioned-release-notes-check:
	scripts/check_versioned_release_notes.sh

release-workflow-check:
	scripts/check_release_workflow.sh

release-evidence-check:
	scripts/check_published_release_evidence.sh

image-size-check:
	RETOS_REQUIRE_BUILT_IMAGES=1 scripts/check_image_size.sh

docker-up:
	docker compose up --build

docker-down:
	docker compose down
