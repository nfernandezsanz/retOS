# Evaluation Harness

RetOS evals are local-first and cost-safe by default. The smoke suite exercises the
retrieval and citation path without network access, external datasets, or paid model
calls.

## Commands

Run the deterministic smoke suite:

```bash
make eval-smoke
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
```

Run an opt-in SQuAD 2.0 dataset eval from a local file:

```bash
make eval-squad SQUAD_PATH=evals/datasets/dev-v2.0.json MAX_CASES=50
```

or directly:

```bash
cd backend
PYTHONPATH=src python scripts/run_eval_smoke.py \
  --suite squad \
  --dataset-path ../evals/datasets/dev-v2.0.json \
  --max-cases 50 \
  --format markdown
```

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

The React console uses these endpoints in the `Local evals` panel to show metrics,
per-case status, and a newest-first run history.

## Public Dataset Roadmap

Do not vendor large benchmark datasets into this repository. Add adapters that download
or read user-provided dataset files under explicit opt-in commands.

| Dataset | Use | Notes |
| --- | --- | --- |
| [SQuAD 2.0](https://rajpurkar.github.io/SQuAD-explorer/) | Reading comprehension and abstention. | The official page describes answerable and unanswerable questions over Wikipedia passages and links downloads under CC BY-SA 4.0. |
| [Natural Questions](https://ai.google.com/research/NaturalQuestions/) | Real user questions with Wikipedia evidence. | The official Google page describes questions from real users requiring systems to read a Wikipedia article; the public GitHub repository is Apache-2.0. |
| [HotpotQA](https://hotpotqa.github.io/) | Multi-hop retrieval and supporting-fact evaluation. | The official benchmark focuses on natural multi-hop questions and supporting facts for explainability. |

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
- Invalid or non-v2 dataset files fail fast with explicit errors.
- Tests use tiny generated fixtures, not vendored benchmark data.

## Adapter Rules

- Adapters must be optional and skipped unless dataset paths are provided.
- CI must not download public datasets by default.
- Tests must use tiny fixtures or generated subsets.
- Paid LLM calls remain disabled unless a live-eval profile is explicitly enabled.
- Reports should be written as JSON plus Markdown summaries under `evals/reports/`.
- Any dataset cache directory must stay out of git.

## Next Implementation Step

The next eval slice should add persisted JSON/Markdown report export for dataset-backed
runs:

```text
dataset file -> EvalCase[] -> local index -> scorer -> evals/reports/*.json + *.md
```

After that, add Natural Questions or HotpotQA adapters for larger retrieval and multi-hop
coverage.
