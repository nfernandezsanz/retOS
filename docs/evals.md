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
report paths, and a newest-first run history. It can also compare the latest two
reported runs through:

```bash
curl "http://localhost:8000/evals/runs/compare?baseline_job_id=<old_job_id>&candidate_job_id=<new_job_id>" \
  --header "Authorization: Bearer <token>"
```

Comparison is local and deterministic. It reads already persisted `eval.run` report
payloads, returns baseline/candidate summaries, per-metric deltas, an average delta,
and a coarse status of `improved`, `regressed`, or `unchanged`.

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

`dataset_path` may be relative or absolute, but it must resolve inside
`RETOS_EVAL_DATASET_ROOT`. Reports are written only when `write_report=true`, and
always land under `RETOS_EVAL_REPORT_ROOT` as both JSON and Markdown. This keeps
benchmark inputs and generated reports mounted, auditable, and outside the source tree.

## Public Dataset Roadmap

Do not vendor large benchmark datasets into this repository. Add adapters that download
or read user-provided dataset files under explicit opt-in commands.

| Dataset | Use | Notes |
| --- | --- | --- |
| [SQuAD 2.0](https://rajpurkar.github.io/SQuAD-explorer/) | Reading comprehension and abstention. | The official page describes answerable and unanswerable questions over Wikipedia passages and links downloads under CC BY-SA 4.0. |
| [Natural Questions](https://ai.google.com/research/NaturalQuestions/) | Implemented for real user questions with Wikipedia evidence. | The official Google page describes questions from real users requiring systems to read a Wikipedia article; the public GitHub repository is Apache-2.0. |
| [HotpotQA](https://hotpotqa.github.io/) | Implemented for multi-hop retrieval and supporting-fact evaluation. | The official benchmark focuses on natural multi-hop questions and supporting facts for explainability. |
| [FUNSD](https://guillaumejaume.github.io/FUNSD/) | Form understanding and OCR/layout pressure. | Useful once RetOS stores page-level OCR artifacts and layout metadata. |
| [ICDAR 2019 SROIE](https://rrc.cvc.uab.es/?ch=13) | Receipt OCR and key information extraction. | Useful for scanned-document extraction quality and audit traces. |
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
  report paths in the durable eval job payload.
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
  report paths in the durable eval job payload.
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
  persist report paths in the durable eval job payload.
- Malformed JSONL lines, missing annotations, invalid token spans, and missing document
  text fail fast with explicit errors.
- Tests use tiny generated fixtures, not vendored benchmark data.

## Adapter Rules

- Adapters must be optional and skipped unless dataset paths are provided.
- CI must not download public datasets by default.
- Tests must use tiny fixtures or generated subsets.
- Paid LLM calls remain disabled unless a live-eval profile is explicitly enabled.
- Reports should be written as JSON plus Markdown summaries under `evals/reports/`
  with explicit stems for named runs.
- Any dataset cache directory must stay out of git.

## Next Implementation Step

Wire OCR benchmark adapters into the persisted eval run history and React comparison view
using the existing page-level OCR artifacts.
