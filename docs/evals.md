# Evaluation Harness

RetOS evals are local-first and cost-safe by default. The smoke suite exercises the
retrieval and citation path without network access, external datasets, or paid model
calls.

## Commands

Run the deterministic smoke suite:

```bash
make eval-smoke
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

HotpotQA and Natural Questions use the same report flags with `--suite hotpotqa` and
`--suite natural-questions`.

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
SQuAD, HotpotQA, and Natural Questions evals, show metrics, per-case status, exported
report paths, and a newest-first run history. Each history row can rerun the persisted
suite when its stored payload still contains the dataset and threshold settings needed
for a faithful repeat:

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
and a coarse status of `improved`, `regressed`, or `unchanged`.

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

Dataset-backed SQuAD evals are also available through the admin API:

```bash
curl --request POST http://localhost:8000/evals/squad \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{
    "dataset_path":"dev-v2.0.json",
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
    "max_cases":50,
    "write_report":true,
    "report_stem":"hotpotqa-dev-50"
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

## Public Dataset Roadmap

Do not vendor large benchmark datasets into this repository. Add adapters that download
or read user-provided dataset files under explicit opt-in commands.

Small public dataset samples can be prepared with:

```bash
make eval-fetch-dataset PROFILE=squad-dev-v2 MAX_RECORDS=100
make eval-fetch-dataset PROFILE=hotpotqa-dev-distractor MAX_RECORDS=100
make eval-fetch-dataset PROFILE=nq-open-train MAX_RECORDS=100
make eval-fetch-dataset PROFILE=nq-open-train-adapter MAX_RECORDS=100
```

The fetcher writes bounded samples under `evals/datasets/`, refuses to overwrite files
unless `FORCE=1` is provided, and is never part of the default CI path. Available
profiles:

| Profile | Output | Notes |
| --- | --- | --- |
| `squad-dev-v2` | `squad-dev-v2-sample.json` | Directly usable with `make eval-squad SQUAD_PATH=evals/datasets/squad-dev-v2-sample.json`. |
| `hotpotqa-dev-distractor` | `hotpotqa-dev-distractor-sample.json` | Directly usable with `make eval-hotpotqa HOTPOTQA_PATH=evals/datasets/hotpotqa-dev-distractor-sample.json`. |
| `nq-open-train` | `nq-open-train-sample.jsonl` | Raw NQ-Open sample for research inspection. |
| `nq-open-train-adapter` | `nq-open-train-adapter-sample.jsonl` | Converts NQ-Open questions and answers into the local RetOS Natural Questions adapter shape with synthetic evidence documents; directly usable with `make eval-natural-questions NQ_PATH=evals/datasets/nq-open-train-adapter-sample.jsonl`. |
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
full document-shape Natural Questions adapter remains the stronger retrieval benchmark
when annotated data is available.

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
- Paid LLM calls remain disabled unless a live-eval profile is explicitly enabled.
- Reports should be written as JSON plus Markdown summaries under `evals/reports/`
  with explicit stems for named runs.
- Any dataset cache directory must stay out of git.

## Next Implementation Step

Use the geometric OCR metrics in larger real-dataset evaluation profiles and add
operator-facing trend views for layout regressions.
