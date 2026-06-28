import gzip
import importlib.util
import io
import json
import sys
from pathlib import Path
from types import ModuleType

from retos.evals.datasets import load_natural_questions_cases


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
    assert "nq-open-train-adapter" in table
    assert "nq-simplified-local" in table
    assert "funsd" in table
    assert fetcher.DATASET_PROFILES["hotpotqa-dev-distractor"].mirror_urls


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


def test_fetcher_samples_gzipped_jsonl(tmp_path: Path) -> None:
    fetcher = load_fetcher()
    source = tmp_path / "nq.jsonl.gz"
    destination = tmp_path / "nq-sample.jsonl"
    with gzip.open(source, "wt", encoding="utf-8") as handle:
        handle.write('{"id": 1}\n{"id": 2}\n{"id": 3}\n')

    count = fetcher.write_jsonl_sample(source, destination, 2)

    assert count == 2
    assert destination.read_text(encoding="utf-8").splitlines() == [
        '{"id": 1}',
        '{"id": 2}',
    ]


def test_fetcher_converts_nq_open_to_adapter_shape(tmp_path: Path) -> None:
    fetcher = load_fetcher()
    source = tmp_path / "nq-open.jsonl"
    destination = tmp_path / "nq-adapter.jsonl"
    source.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "question": "who wrote the moon memo",
                        "answer": ["Ada Lovelace"],
                    }
                ),
                json.dumps({"question": "missing answer", "answer": []}),
                json.dumps(
                    {
                        "question_text": "who reviewed the launch notes",
                        "answers": ["Katherine Johnson"],
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    count = fetcher.write_nq_open_adapter_sample(source, destination, 2)

    assert count == 2
    records = [
        json.loads(line)
        for line in destination.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert records[0]["question_text"] == "who wrote the moon memo"
    assert records[0]["document_text"] == "Answer: Ada Lovelace"
    assert records[0]["annotations"][0]["long_answer"] == {
        "start_token": 0,
        "end_token": 3,
    }
    assert records[0]["annotations"][0]["short_answers"] == [{"start_token": 1, "end_token": 3}]
    cases = load_natural_questions_cases(destination)
    assert len(cases) == 2
    assert cases[0].expected_answer_terms == ("Ada Lovelace",)


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
    assert result["source_url"] == fetcher.DATASET_PROFILES["squad-dev-v2"].url
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


def test_fetch_profile_uses_dataset_mirror_when_primary_download_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    fetcher = load_fetcher()
    payload = json.dumps([{"_id": "case-1"}, {"_id": "case-2"}]).encode()
    primary_url = "https://example.invalid/primary.json"
    mirror_url = "https://example.test/mirror.json"
    calls: list[str] = []

    class FakeResponse:
        def __init__(self) -> None:
            self.stream = io.BytesIO(payload)

        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, size: int = -1) -> bytes:
            return self.stream.read(size)

    def fake_urlopen(url: str, **_: object) -> FakeResponse:
        calls.append(url)
        if url == primary_url:
            raise fetcher.urllib.error.URLError("primary unavailable")
        return FakeResponse()

    profile = fetcher.DatasetProfile(
        name="mirror-fixture",
        suite="hotpotqa",
        url=primary_url,
        output_name="mirror-sample.json",
        description="Mirror test fixture",
        license_note="Fixture license",
        source_homepage="https://example.test",
        sampler=lambda src, dest, limit: fetcher.write_json_list_sample(src, dest, limit),
        mirror_urls=(mirror_url,),
    )
    monkeypatch.setattr(fetcher.urllib.request, "urlopen", fake_urlopen)

    result = fetcher.fetch_profile(
        profile=profile,
        output_dir=tmp_path,
        max_records=1,
        download_retries=1,
    )

    assert calls == [primary_url, mirror_url]
    assert result["source_url"] == mirror_url
    assert json.loads(Path(result["path"]).read_text(encoding="utf-8")) == [{"_id": "case-1"}]


def test_fetch_profile_can_write_nq_open_adapter_sample(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    fetcher = load_fetcher()
    payload = (
        json.dumps({"question": "who found the comet", "answer": ["Caroline Herschel"]}) + "\n"
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
        profile=fetcher.DATASET_PROFILES["nq-open-train-adapter"],
        output_dir=tmp_path,
        max_records=1,
    )

    assert result["suite"] == "natural-questions"
    output_path = Path(result["path"])
    cases = load_natural_questions_cases(output_path)
    assert cases[0].expected_answer_terms == ("Caroline Herschel",)


def test_fetch_profile_can_sample_local_simplified_nq_gzip(tmp_path: Path) -> None:
    fetcher = load_fetcher()
    source = tmp_path / "simplified-nq-dev.jsonl.gz"
    source_item = {
        "example_id": 987,
        "question_text": "Which mission landed at Tranquility Base?",
        "document_title": "Apollo 11",
        "document_tokens": [
            {"token": "<P>", "html_token": True},
            {"token": "Apollo", "html_token": False},
            {"token": "11", "html_token": False},
            {"token": "landed", "html_token": False},
            {"token": "at", "html_token": False},
            {"token": "Tranquility", "html_token": False},
            {"token": "Base", "html_token": False},
        ],
        "annotations": [
            {
                "long_answer": {"start_token": 1, "end_token": 7},
                "short_answers": [{"start_token": 1, "end_token": 3}],
                "yes_no_answer": "NONE",
            }
        ],
    }
    with gzip.open(source, "wt", encoding="utf-8") as handle:
        handle.write(json.dumps(source_item) + "\n")

    result = fetcher.fetch_profile(
        profile=fetcher.DATASET_PROFILES["nq-simplified-local"],
        output_dir=tmp_path / "samples",
        max_records=1,
        source_path=source,
    )

    assert result["profile"] == "nq-simplified-local"
    assert result["source_path"] == str(source)
    cases = load_natural_questions_cases(Path(result["path"]))
    assert len(cases) == 1
    assert cases[0].documents[0].text == "Apollo 11 landed at Tranquility Base"
    assert cases[0].expected_answer_terms == ("Apollo 11",)


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
            profile=fetcher.DATASET_PROFILES["funsd"],
            output_dir=tmp_path,
            max_records=10,
            source_path=tmp_path / "funsd.zip",
        )
    except fetcher.DatasetFetchError as exc:
        assert "single source file" in str(exc)
    else:
        raise AssertionError("Expected file-backed FUNSD sampling to fail")

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

    try:
        fetcher.fetch_profile(
            profile=fetcher.DATASET_PROFILES["squad-dev-v2"],
            output_dir=tmp_path,
            max_records=1,
            download_timeout=0,
        )
    except fetcher.DatasetFetchError as exc:
        assert "download-timeout" in str(exc)
    else:
        raise AssertionError("Expected invalid download timeout to fail")

    try:
        fetcher.fetch_profile(
            profile=fetcher.DATASET_PROFILES["squad-dev-v2"],
            output_dir=tmp_path,
            max_records=1,
            download_retries=0,
        )
    except fetcher.DatasetFetchError as exc:
        assert "download-retries" in str(exc)
    else:
        raise AssertionError("Expected invalid download retries to fail")
