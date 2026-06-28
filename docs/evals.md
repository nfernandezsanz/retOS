# Evaluation Harness

RetOS evals are local-first and cost-safe by default. The smoke suite exercises the
retrieval and citation path without network access, external datasets, or paid model
calls.

## Commands

Run the deterministic smoke suite:

```bash
make eval-smoke
```

Run the deterministic agent multi-hop suite:

```bash
make eval-agent-multihop
```

Run the opt-in local OCR quality smoke suite:

```bash
make eval-ocr
```

Run an opt-in OCR benchmark suite from a local manifest, FUNSD directory, or SROIE
directory:

```bash
make eval-ocr-benchmark OCR_PATH=evals/datasets/ocr-benchmark/manifest.json
make eval-ocr-benchmark OCR_PATH=evals/datasets/funsd OCR_FORMAT=funsd MAX_CASES=25
make eval-ocr-benchmark OCR_PATH=evals/datasets/sroie OCR_FORMAT=sroie MAX_CASES=25
```

Run the backend quality gate, including eval smoke:

```bash
make check
```

The underlying CLI supports JSON or Markdown output:

```bash
cd backend
PYTHONPATH=src python scripts/run_eval_smoke.py --format json
PYTHONPATH=src python scripts/run_eval_smoke.py --format markdown
PYTHONPATH=src python scripts/run_eval_smoke.py --suite agent-multihop --format markdown
PYTHONPATH=src python scripts/run_eval_smoke.py --suite ocr-smoke --format markdown
PYTHONPATH=src python scripts/run_eval_smoke.py \
  --suite ocr-benchmark \
  --dataset-path ../evals/datasets/ocr-benchmark/manifest.json \
  --dataset-format manifest \
  --max-cases 25 \
  --format markdown
```

Run an opt-in SQuAD 2.0 dataset eval from a local file:

```bash
make eval-squad SQUAD_PATH=evals/datasets/dev-v2.0.json MAX_CASES=50
```

Run an opt-in HotpotQA dataset eval from a local file:

```bash
make eval-hotpotqa HOTPOTQA_PATH=evals/datasets/hotpot_dev_distractor_v1.json MAX_CASES=50
```

Run HotpotQA supporting facts through the agent audit harness:

```bash
make eval-hotpotqa-agent HOTPOTQA_PATH=evals/datasets/hotpot_dev_distractor_v1.json MAX_CASES=50
```

Run an opt-in Natural Questions dataset eval from a local JSONL or JSON file:

```bash
make eval-natural-questions NQ_PATH=evals/datasets/nq-dev-sample.jsonl MAX_CASES=50
```

Persist both JSON and Markdown reports:

```bash
make eval-squad \
  SQUAD_PATH=evals/datasets/dev-v2.0.json \
  MAX_CASES=50 \
  REPORT_DIR=evals/reports \
  REPORT_STEM=squad-v2-dev-50
```

or directly:

```bash
cd backend
PYTHONPATH=src python scripts/run_eval_smoke.py \
  --suite squad \
  --dataset-path ../evals/datasets/dev-v2.0.json \
  --max-cases 50 \
  --report-dir ../evals/reports \
  --report-stem squad-v2-dev-50 \
  --format markdown
```

HotpotQA, HotpotQA agent, and Natural Questions use the same report flags with
`--suite hotpotqa`, `--suite hotpotqa-agent`, and `--suite natural-questions`.

Dataset-backed JSON and Markdown reports include a `metadata` block with the adapter,
resolved dataset path, requested `max_cases`, and execution source. Built-in smoke
reports identify their fixture source. The API persists the same metadata under the
eval job payload and journal/progress events so comparison and audit reviews can trace a
metric back to the exact dataset input without opening the original command transcript.

## What The Smoke Suite Measures

The built-in suite creates a temporary Tantivy index and evaluates fixture cases for:

| Metric | Meaning |
| --- | --- |
| Retrieval recall | Expected supporting documents appear in retrieved hits. |
| Citation validity | Returned citations point to known fixture segments with anchors. |
| Grounded answer | Required evidence terms appear in the generated answer. |
| Abstention | Missing evidence produces a no-answer response. |
| Budget compliance | Returned citations stay within the case budget. |

The suite exits non-zero if any case fails.

## Agent Multi-Hop Eval

The built-in agent suite creates a temporary Tantivy index and exercises the same
bounded planned-search helper used by `agent.query`. It validates deterministic
multi-hop query planning, bounded subquery execution, multi-document evidence-route
coverage, bridge-term support, citation validity, grounded answer terms, and budget
compliance.

It is safe for CI because it does not call Ollama, OpenAI, Anthropic, or any paid
provider:

```bash
PYTHONPATH=src python scripts/run_eval_smoke.py --suite agent-multihop --format markdown
```

Current built-in cases cover:

| Case | Calibration Target |
| --- | --- |
| `apollo-telemetry-bridge` | Cross-document bridge terms for checklist and telemetry guidance. |
| `invoice-retention-policy` | Policy evidence that must connect invoice approval with retention review. |
| `incident-escalation-triage` | Incident response evidence with a strict two-citation budget. |

The same suite is available through the admin API at `/evals/agent-multihop`. API runs
persist an `eval.run` job, report metrics, journal/progress events, and support reruns
through `/evals/runs/<job_id>/rerun`.

## OCR Quality

`make eval-ocr` generates tiny image-only PDFs locally, runs them through the same OCR
function used by ingestion, and scores the extracted text with:

| Metric | Meaning |
| --- | --- |
| Character error rate | Edit distance over normalized characters, useful for punctuation and spelling drift. |
| Word error rate | Edit distance over normalized word tokens, useful for searchable evidence quality. |
| Key-value recall | Optional field-level recall for forms and receipts. A case contributes this metric when it declares expected key/value pairs. |

The suite is opt-in because real OCR depends on local Tesseract availability and
host-specific rendering behavior. Unit tests mock the OCR adapter so CI coverage stays
deterministic, local, and free.

## API And UI

The same smoke suite is available through the API:

```bash
curl --request POST http://localhost:8000/evals/smoke \
  --header "Authorization: Bearer <token>"
```

The API creates a durable `eval.run` job, persists the report under `job.payload.result`,
writes journal/progress events, and returns the report immediately. Recent persisted
runs are available through:

```bash
curl "http://localhost:8000/evals/runs?limit=6" \
  --header "Authorization: Bearer <token>"
```

The React console uses these endpoints in the `Local evals` panel to run smoke,
agent multi-hop, SQuAD, HotpotQA, Natural Questions, and OCR benchmark evals, show
metrics, per-case status, exported report paths, dataset provenance metadata, and a
newest-first run history. The `Eval scope` selector keeps dataset-backed requests and
history/trends auditable: `All evals` saves new dataset runs as global runs and reads
unfiltered history, while selecting a domain sends `domain_id` and filters history,
trends, comparison, and regression-gate inputs to that domain. Each history row can
rerun the persisted suite when its stored payload still contains the dataset and
threshold settings needed for a faithful repeat:

```bash
curl --request POST "http://localhost:8000/evals/runs/<job_id>/rerun" \
  --header "Authorization: Bearer <token>"
```

Reruns create a new `eval.run` job and store `rerun_from_job_id` in the new payload,
so auditors can link the repeated execution to the original report. The console can
also compare the latest two reported runs through:

```bash
curl "http://localhost:8000/evals/runs/compare?baseline_job_id=<old_job_id>&candidate_job_id=<new_job_id>" \
  --header "Authorization: Bearer <token>"
```

Comparison is local and deterministic. It reads already persisted `eval.run` report
payloads, returns baseline/candidate summaries, per-metric deltas, an average delta,
and a coarse status of `improved`, `regressed`, or `unchanged`. The React console exposes
this as `Compare latest` for the two newest reported runs.

Operator-facing trends are available through:

```bash
curl "http://localhost:8000/evals/runs/trends?limit=60" \
  --header "Authorization: Bearer <token>"
```

The trend endpoint groups persisted reported runs by suite, returns chronological
points, pass rate, latest run summary, and per-metric first/latest/min/max/average
deltas. Metrics ending in `error_rate` are treated as lower-is-better when assigning
`improved`, `regressed`, or `unchanged` direction. The React console renders these
suite trends in the `Local evals` panel beside history, comparison, and rerun controls.

Use the persisted regression gate before promoting larger real-dataset calibration
runs:

```bash
curl "http://localhost:8000/evals/runs/regression-gate?baseline_job_id=<old_job_id>&candidate_job_id=<new_job_id>&metric_drop_tolerance=0.02&average_drop_tolerance=0.01" \
  --header "Authorization: Bearer <token>"
```

The gate is local and cost-safe. It reads existing `eval.run` reports, normalizes metric
direction so lower-is-better OCR error rates are handled correctly, and returns
`passed=false` when any metric exceeds the allowed drop or when the average normalized
delta drops beyond tolerance. The React console exposes this as `Regression gate` using
the same newest candidate and previous baseline pair, with a default 2% per-metric
tolerance and 1% average tolerance. Baseline and candidate runs must share the same
domain scope.

Dataset-backed SQuAD evals are also available through the admin API:

```bash
curl --request POST http://localhost:8000/evals/squad \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{
    "dataset_path":"dev-v2.0.json",
    "domain_id":"<optional_domain_id>",
    "max_cases":50,
    "write_report":true,
    "report_stem":"squad-v2-dev-50"
  }'
```

Dataset-backed HotpotQA evals use the same request body against `/evals/hotpotqa`:

```bash
curl --request POST http://localhost:8000/evals/hotpotqa \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{
    "dataset_path":"hotpot_dev_distractor_v1.json",
    "domain_id":"<optional_domain_id>",
    "max_cases":50,
    "write_report":true,
    "report_stem":"hotpotqa-dev-50"
  }'
```

HotpotQA supporting-fact agent audit evals use the same request body against
`/evals/hotpotqa-agent`:

```bash
curl --request POST http://localhost:8000/evals/hotpotqa-agent \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{
    "dataset_path":"hotpot_dev_distractor_v1.json",
    "domain_id":"<optional_domain_id>",
    "max_cases":50,
    "write_report":true,
    "report_stem":"hotpotqa-agent-dev-50"
  }'
```

Dataset-backed Natural Questions evals use the same request body against
`/evals/natural-questions`:

```bash
curl --request POST http://localhost:8000/evals/natural-questions \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{
    "dataset_path":"nq-dev-sample.jsonl",
    "domain_id":"<optional_domain_id>",
    "max_cases":50,
    "write_report":true,
    "report_stem":"natural-questions-dev-50"
  }'
```

OCR benchmark evals use `/evals/ocr-benchmark` with a local dataset path and a
`dataset_format` of `manifest`, `funsd`, or `sroie`:

```bash
curl --request POST http://localhost:8000/evals/ocr-benchmark \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{
    "dataset_path":"ocr-benchmark/manifest.json",
    "domain_id":"<optional_domain_id>",
    "dataset_format":"manifest",
    "max_cases":25,
    "write_report":true,
    "report_stem":"ocr-manifest-25",
    "max_character_error_rate":0.20,
    "max_word_error_rate":0.35,
    "max_pages":1
  }'
```

`dataset_path` may be relative or absolute, but it must resolve inside
`RETOS_EVAL_DATASET_ROOT`. Reports are written only when `write_report=true`, and
always land under `RETOS_EVAL_REPORT_ROOT` as both JSON and Markdown. This keeps
benchmark inputs and generated reports mounted, auditable, and outside the source tree.
`domain_id` is optional for admins and required for viewers running dataset-backed evals.
When set, RetOS validates the domain grant, stores the scope on the durable eval job and
audit/progress payloads, supports domain-filtered history/trends, preserves the scope on
reruns, and prevents comparison or regression-gate checks across mixed global/domain
scopes. Built-in evals, global evals, comparison, and regression gates remain
admin-only. The React console exposes the same contract through `Eval scope`, and each
run-history row shows whether the persisted report is global or domain-owned.

## Public Dataset Roadmap

Do not vendor large benchmark datasets into this repository. Add adapters that download
or read user-provided dataset files under explicit opt-in commands.

Small public dataset samples can be prepared with:

```bash
make eval-fetch-dataset PROFILE=squad-dev-v2 MAX_RECORDS=100
make eval-fetch-dataset PROFILE=hotpotqa-dev-distractor MAX_RECORDS=100
make eval-fetch-dataset PROFILE=nq-open-train MAX_RECORDS=100
make eval-fetch-dataset PROFILE=nq-open-train-adapter MAX_RECORDS=100
make eval-fetch-dataset PROFILE=nq-simplified-local \
  SOURCE_PATH=/path/to/simplified-nq-dev-all.jsonl.gz MAX_RECORDS=100
```

Run the bounded public calibration set end-to-end:

```bash
make eval-calibration MAX_RECORDS=100 MAX_CASES=50
make eval-calibration TARGET=hotpotqa-agent MAX_RECORDS=100 MAX_CASES=25
make eval-calibration MAX_RECORDS=100 MAX_CASES=50 \
  METRIC_GATES="retrieval_recall=0.80 citation_validity=1.0"
```

The calibration command fetches or reuses bounded samples for SQuAD, HotpotQA,
HotpotQA-agent, and the NQ-Open adapter, then writes per-suite JSON/Markdown reports
plus `evals/reports/calibration/manifest.json`. The manifest records pass/fail status,
case counts, metrics, dataset provenance, report paths, optional metric-gate decisions,
and whether an existing sample was reused. `METRIC_GATES` expands to repeated
`--metric-gate NAME=MINIMUM` CLI flags; every selected target must report each metric at
or above the configured threshold or the manifest fails. Use these gates when turning a
larger real-dataset run into release-promotion evidence. The command is intentionally
opt-in because it performs network downloads when samples are missing, but tests mock
the fetch and eval layers so no CI run depends on public endpoints or paid providers.

The fetcher writes bounded samples under `evals/datasets/`, refuses to overwrite files
unless `FORCE=1` is provided, and is never part of the default CI path. Networked
profiles support `--download-timeout` and `--download-retries`; the Make target can pass
these through as `DOWNLOAD_TIMEOUT` and `DOWNLOAD_RETRIES` when an operator needs
custom values. HTTPS downloads use the bundled `certifi` certificate store so local
Python certificate configuration does not block real-dataset calibration. Fetch results
include `source_url` so reports and release evidence can distinguish the official
primary URL from a configured mirror. Available profiles:

| Profile | Output | Notes |
| --- | --- | --- |
| `squad-dev-v2` | `squad-dev-v2-sample.json` | Directly usable with `make eval-squad SQUAD_PATH=evals/datasets/squad-dev-v2-sample.json`. |
| `hotpotqa-dev-distractor` | `hotpotqa-dev-distractor-sample.json` | Directly usable with `make eval-hotpotqa HOTPOTQA_PATH=evals/datasets/hotpotqa-dev-distractor-sample.json` or `make eval-hotpotqa-agent HOTPOTQA_PATH=evals/datasets/hotpotqa-dev-distractor-sample.json` when the sample contains at least one case with two supporting documents and shared bridge terms. The fetcher tries the official HotpotQA URL first and then a pinned Hugging Face mirror if the primary source is unavailable. |
| `nq-open-train` | `nq-open-train-sample.jsonl` | Raw NQ-Open sample for research inspection. |
| `nq-open-train-adapter` | `nq-open-train-adapter-sample.jsonl` | Converts NQ-Open questions and answers into the local RetOS Natural Questions adapter shape with synthetic evidence documents; directly usable with `make eval-natural-questions NQ_PATH=evals/datasets/nq-open-train-adapter-sample.jsonl`. |
| `nq-simplified-local` | `nq-simplified-sample.jsonl` | Samples an operator-provided official simplified Natural Questions `.jsonl` or `.jsonl.gz` file without network access; directly usable with `make eval-natural-questions NQ_PATH=evals/datasets/nq-simplified-sample.jsonl`. |
| `funsd` | Manual download | Listed with source/license notes; the dataset must be downloaded manually after reviewing the official license. |

| Dataset | Use | Notes |
| --- | --- | --- |
| [SQuAD 2.0](https://rajpurkar.github.io/SQuAD-explorer/) | Reading comprehension and abstention. | The official page describes answerable and unanswerable questions over Wikipedia passages and links downloads under CC BY-SA 4.0. |
| [Natural Questions](https://ai.google.com/research/NaturalQuestions/) | Implemented for real user questions with Wikipedia evidence. | The official Google page describes questions from real users requiring systems to read a Wikipedia article; the public GitHub repository is Apache-2.0. |
| [HotpotQA](https://hotpotqa.github.io/) | Implemented for multi-hop retrieval and supporting-fact evaluation. | The official benchmark focuses on natural multi-hop questions and supporting facts for explainability. |
| [FUNSD](https://guillaumejaume.github.io/FUNSD/) | Implemented as an OCR benchmark adapter for form image/text pressure. | Reads local `annotations/*.json` plus matching files in `images/`; derives key-value recall and layout boxes when annotations provide links and boxes. |
| [ICDAR 2019 SROIE](https://rrc.cvc.uab.es/?ch=13) | Implemented as an OCR benchmark adapter for receipt OCR pressure. | Reads local box/text files plus matching files in `img/` or `images/`; derives key-value recall and layout boxes from local annotation files. |
| [ISRI OCR Evaluation Tools](https://code.google.com/archive/p/isri-ocr-evaluation-tools/) | OCR scoring references. | Useful as a historical reference for OCR error-rate methodology and tooling. |

## SQuAD 2.0 Adapter

The SQuAD adapter reads the official JSON shape from a local file:

```text
data[] -> paragraphs[] -> qas[]
```

For answerable questions, the adapter creates one `EvalCase` with the paragraph context
as the only document, the article title as the expected citation title, and the first
official answer text as the expected grounded term. For impossible questions, it creates
an abstention case with no indexed documents, which exercises RetOS no-evidence behavior
without requiring a paid model to judge answerability inside a related paragraph.

Adapter guarantees:

- No network access.
- No paid model calls.
- `--max-cases` bounds runtime for local experiments.
- `--report-dir` writes reproducible JSON and Markdown report artifacts.
- `POST /evals/squad` can run the same adapter through the admin API and persist
  report paths and rerunnable dataset settings in the durable eval job payload.
- Invalid or non-v2 dataset files fail fast with explicit errors.
- Tests use tiny generated fixtures, not vendored benchmark data.

## HotpotQA Adapter

The HotpotQA adapter reads the official distractor/fullwiki JSON shape from a local
file:

```text
[] -> {_id, question, answer, supporting_facts, context}
context[] -> [title, [sentences]]
supporting_facts[] -> [title, sentence_id]
```

Each case becomes one `EvalCase` with every context paragraph indexed as a document.
The expected citation titles are the unique supporting-fact titles, so retrieval recall
checks whether RetOS brought back the documents needed for multi-hop evidence. The
expected grounded term is the official answer except for `yes`, `no`, and `noanswer`,
which are too generic for deterministic term matching.

Adapter guarantees:

- No network access.
- No paid model calls.
- `--max-cases` bounds runtime for local experiments.
- `POST /evals/hotpotqa` can run the same adapter through the admin API and persist
  report paths and rerunnable dataset settings in the durable eval job payload.
- Missing supporting contexts and malformed `context` or `supporting_facts` entries
  fail fast with explicit errors.
- Tests use tiny generated fixtures, not vendored benchmark data.

## HotpotQA Agent Adapter

`make eval-hotpotqa-agent` and `POST /evals/hotpotqa-agent` read the same local
HotpotQA JSON shape, but convert eligible cases into `AgentEvalCase` records for the
deterministic agent audit harness. The adapter keeps only cases with at least two
supporting documents and shared bridge terms between those supporting documents, then
wraps the original question in a comparison prompt so RetOS must exercise the
multi-hop query planner.

The resulting report uses the `hotpotqa-agent` suite name and scores:

- query-plan strategy and planned search fanout
- multi-document support and bridge terms
- evidence-route coverage
- citation validity
- grounded answer terms
- search/citation/evidence-token budget compliance

API runs persist durable `eval.run` jobs, report paths, dataset provenance, domain
scope, journal/progress events, and `rerun_from_job_id` traceability. The React eval
panel exposes this profile beside the standard HotpotQA retrieval eval. It remains
cost-safe: no network access,
no paid provider calls, bounded `MAX_CASES`, and reproducible JSON/Markdown reports.

## Natural Questions Adapter

The Natural Questions adapter reads local JSONL, `.jsonl.gz`, JSON arrays, or JSON objects
that follow the official Google Research shape:

```text
{example_id, question_text, document_text|document_tokens, annotations}
annotations[] -> {long_answer, short_answers, yes_no_answer}
```

Each answerable case becomes one `EvalCase` with the annotated long-answer span as the
indexed document. The expected citation title comes from `document_title`, `title`, or
the final segment of `document_url`. Short-answer spans become grounded answer terms;
`YES`/`NO` answers are kept as retrieval/citation cases without brittle term checks. Cases
with no valid long answer become abstention cases when unanswerable examples are enabled.

Adapter guarantees:

- No network access.
- No paid model calls.
- `--max-cases` bounds runtime for local experiments.
- `POST /evals/natural-questions` can run the same adapter through the admin API and
  persist report paths and rerunnable dataset settings in the durable eval job payload.
- Malformed JSONL lines, missing annotations, invalid token spans, and missing document
  text fail fast with explicit errors.
- Tests use tiny generated fixtures, not vendored benchmark data.

The `nq-open-train-adapter` fetch profile is a pragmatic bridge for early real-question
calibration. NQ-Open does not include the full annotated Wikipedia document shape, so the
fetcher creates a bounded JSONL sample with synthetic local evidence documents containing
the provided answer. This is useful for query-shape and answer-term regression, while the
full document-shape Natural Questions adapter remains the stronger retrieval benchmark.

For the full document-shape path, download the official simplified Natural Questions file
after reviewing Google's dataset access terms, then sample it locally:

```bash
make eval-fetch-dataset PROFILE=nq-simplified-local \
  SOURCE_PATH=/path/to/simplified-nq-dev-all.jsonl.gz \
  MAX_RECORDS=100
make eval-natural-questions \
  NQ_PATH=evals/datasets/nq-simplified-sample.jsonl \
  MAX_CASES=50 \
  REPORT_DIR=evals/reports
```

The `SOURCE_PATH` flow accepts `.jsonl` and `.jsonl.gz` inputs, writes a bounded JSONL
sample under `evals/datasets/`, refuses overwrites unless `FORCE=1` is provided, and keeps
the networked dataset outside default CI.

## OCR Benchmark Adapters

OCR benchmark adapters create `OCRQualityCase` inputs for the same OCR scorer used by
`make eval-ocr`. They never download datasets and they require every input file to stay
inside the dataset root.

Supported formats:

| Format | Input path | Contract |
| --- | --- | --- |
| `manifest` | JSON file | Root object with `cases[]`, or a root list. Each case requires `case_id`, `input_path`, and `expected_text`. Cases may include `expected_key_values` and `expected_layout[]` with `{text, bbox, page_number}` entries. Relative `input_path` values resolve beside the manifest. |
| `funsd` | Dataset directory | Reads `annotations/*.json`, joins non-empty `form[].text`, derives key/value pairs from `question` to `answer` links when present, derives layout boxes from `form[].box`, and resolves matching `.pdf`, `.png`, `.jpg`, `.jpeg`, `.tif`, or `.tiff` files from `images/`. |
| `sroie` | Dataset directory | Reads text files from `box/`, `boxes/`, `ocr/`, or `text/`, extracts text and bounding polygons from each line, reads optional entities from `entities/`, `entity/`, `key/`, or `keys/`, and resolves matching files from `img/` or `images/`. |

Images are converted to temporary PDFs before OCR so the adapter reuses the ingestion
OCR path rather than introducing a parallel image OCR implementation.

Key-value recall and layout scoring are intentionally deterministic and local. The
scorer normalizes OCR text, labels, and values; a field counts as found when both label
and value appear in the OCR text and the label appears before the value. When expected
layout boxes are available, the suite also runs Tesseract word-box extraction and
reports:

- `reading_order_accuracy`: pairwise expected box order preserved by OCR output order.
- `layout_iou`: average intersection-over-union for matched expected and actual boxes.

Layout scoring is opt-in per case. Cases without `expected_layout` keep reporting only
CER/WER and optional key-value recall.

## Adapter Rules

- Adapters must be optional and skipped unless dataset paths are provided.
- CI must not download public datasets by default.
- Tests must use tiny fixtures or generated subsets.
- Networked fetchers must keep configured mirrors auditable through `source_url`.
- Paid LLM calls remain disabled unless a live-eval profile is explicitly enabled.
- Reports should be written as JSON plus Markdown summaries under `evals/reports/`
  with explicit stems for named runs.
- Any dataset cache directory must stay out of git.

## Next Implementation Step

Expand real-dataset eval trend calibration and connect persisted eval evidence to
release promotion gates.
