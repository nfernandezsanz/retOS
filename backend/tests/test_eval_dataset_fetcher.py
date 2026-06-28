import importlib.util
import io
import json
import sys
from pathlib import Path
from types import ModuleType


def load_fetcher() -> ModuleType:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "fetch_eval_dataset.py"
    spec = importlib.util.spec_from_file_location("fetch_eval_dataset", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load dataset fetcher from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_fetcher_lists_public_profiles() -> None:
    fetcher = load_fetcher()

    table = fetcher.profile_table()

    assert "squad-dev-v2" in table
    assert "hotpotqa-dev-distractor" in table
    assert "nq-open-train" in table
    assert "funsd" in table


def test_fetcher_samples_squad_fixture(tmp_path: Path) -> None:
    fetcher = load_fetcher()
    source = tmp_path / "dev-v2.0.json"
    destination = tmp_path / "sample.json"
    source.write_text(
        json.dumps(
            {
                "version": "v2.0",
                "data": [
                    {
                        "title": "Article",
                        "paragraphs": [
                            {
                                "context": "Mars is red.",
                                "qas": [
                                    {"id": "q1", "question": "Q1"},
                                    {"id": "q2", "question": "Q2"},
                                ],
                            },
                            {
                                "context": "Venus is bright.",
                                "qas": [{"id": "q3", "question": "Q3"}],
                            },
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    count = fetcher.write_squad_sample(source, destination, 2)

    sampled = json.loads(destination.read_text(encoding="utf-8"))
    assert count == 2
    assert sampled["version"] == "v2.0"
    assert sampled["data"][0]["paragraphs"][0]["qas"] == [
        {"id": "q1", "question": "Q1"},
        {"id": "q2", "question": "Q2"},
    ]
    assert len(sampled["data"][0]["paragraphs"]) == 1


def test_fetcher_samples_json_list_and_jsonl(tmp_path: Path) -> None:
    fetcher = load_fetcher()
    list_source = tmp_path / "hotpot.json"
    list_destination = tmp_path / "hotpot-sample.json"
    jsonl_source = tmp_path / "nq.jsonl"
    jsonl_destination = tmp_path / "nq-sample.jsonl"
    list_source.write_text(json.dumps([{"id": 1}, {"id": 2}, {"id": 3}]), encoding="utf-8")
    jsonl_source.write_text('{"id": 1}\n\n{"id": 2}\n{"id": 3}\n', encoding="utf-8")

    list_count = fetcher.write_json_list_sample(list_source, list_destination, 2)
    jsonl_count = fetcher.write_jsonl_sample(jsonl_source, jsonl_destination, 2)

    assert list_count == 2
    assert json.loads(list_destination.read_text(encoding="utf-8")) == [{"id": 1}, {"id": 2}]
    assert jsonl_count == 2
    assert jsonl_destination.read_text(encoding="utf-8").splitlines() == [
        '{"id": 1}',
        '{"id": 2}',
    ]


def test_fetch_profile_downloads_and_samples_without_overwriting(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    fetcher = load_fetcher()
    payload = json.dumps(
        {
            "version": "v2.0",
            "data": [
                {
                    "title": "Article",
                    "paragraphs": [
                        {
                            "context": "Mars is red.",
                            "qas": [
                                {"id": "q1", "question": "Q1"},
                                {"id": "q2", "question": "Q2"},
                            ],
                        }
                    ],
                }
            ],
        }
    ).encode()

    class FakeResponse:
        def __init__(self) -> None:
            self.stream = io.BytesIO(payload)

        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, size: int = -1) -> bytes:
            return self.stream.read(size)

    monkeypatch.setattr(fetcher.urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse())

    result = fetcher.fetch_profile(
        profile=fetcher.DATASET_PROFILES["squad-dev-v2"],
        output_dir=tmp_path,
        max_records=1,
    )

    assert result["profile"] == "squad-dev-v2"
    assert result["records"] == 1
    output_path = Path(result["path"])
    assert output_path.exists()
    assert json.loads(output_path.read_text(encoding="utf-8"))["data"][0]["paragraphs"][0][
        "qas"
    ] == [{"id": "q1", "question": "Q1"}]

    try:
        fetcher.fetch_profile(
            profile=fetcher.DATASET_PROFILES["squad-dev-v2"],
            output_dir=tmp_path,
            max_records=1,
        )
    except fetcher.DatasetFetchError as exc:
        assert "overwrite" in str(exc)
    else:
        raise AssertionError("Expected overwrite protection to fail")


def test_fetch_profile_rejects_manual_and_invalid_profiles(tmp_path: Path) -> None:
    fetcher = load_fetcher()

    try:
        fetcher.fetch_profile(
            profile=fetcher.DATASET_PROFILES["funsd"],
            output_dir=tmp_path,
            max_records=10,
        )
    except fetcher.DatasetFetchError as exc:
        assert "manual download" in str(exc)
    else:
        raise AssertionError("Expected manual profile to fail")

    try:
        fetcher.fetch_profile(
            profile=fetcher.DATASET_PROFILES["squad-dev-v2"],
            output_dir=tmp_path,
            max_records=0,
        )
    except fetcher.DatasetFetchError as exc:
        assert "greater than zero" in str(exc)
    else:
        raise AssertionError("Expected non-positive max records to fail")
