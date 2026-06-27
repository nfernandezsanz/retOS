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
writes journal/progress events, and returns the report immediately. The React console
uses this endpoint in the `Local evals` panel to show metrics and per-case status.

## Public Dataset Roadmap

Do not vendor large benchmark datasets into this repository. Add adapters that download
or read user-provided dataset files under explicit opt-in commands.

| Dataset | Use | Notes |
| --- | --- | --- |
| [SQuAD 2.0](https://rajpurkar.github.io/SQuAD-explorer/) | Reading comprehension and abstention. | The official page describes answerable and unanswerable questions over Wikipedia passages and links downloads under CC BY-SA 4.0. |
| [Natural Questions](https://ai.google.com/research/NaturalQuestions/) | Real user questions with Wikipedia evidence. | The official Google page describes questions from real users requiring systems to read a Wikipedia article; the public GitHub repository is Apache-2.0. |
| [HotpotQA](https://hotpotqa.github.io/) | Multi-hop retrieval and supporting-fact evaluation. | The official benchmark focuses on natural multi-hop questions and supporting facts for explainability. |

## Adapter Rules

- Adapters must be optional and skipped unless dataset paths are provided.
- CI must not download public datasets by default.
- Tests must use tiny fixtures or generated subsets.
- Paid LLM calls remain disabled unless a live-eval profile is explicitly enabled.
- Reports should be written as JSON plus Markdown summaries under `evals/reports/`.
- Any dataset cache directory must stay out of git.

## Next Implementation Step

The next eval slice should add a small adapter interface and persisted report listing:

```text
dataset file -> EvalCase[] -> local index -> scorer -> JSON/Markdown report
```

SQuAD 2.0 is the best first adapter because its unanswerable questions map directly to
RetOS abstention scoring.
