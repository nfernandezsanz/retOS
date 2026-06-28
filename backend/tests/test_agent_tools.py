import pytest

from retos.agent.tools import CorpusToolError, create_corpus_toolbox
from retos.search.index import SearchHit


class FakeSearchIndex:
    def __init__(self, hits: list[SearchHit]) -> None:
        self.hits = hits
        self.calls: list[tuple[str, str, int]] = []

    def search_domain(self, domain_id: str, query_text: str, *, limit: int) -> list[SearchHit]:
        self.calls.append((domain_id, query_text, limit))
        return self.hits[:limit]


def hit(segment_id: str, text: str) -> SearchHit:
    return SearchHit(
        segment_id=segment_id,
        document_id="document-1",
        document_version_id="version-1",
        title="Fixture",
        text=text,
        anchor="page=1",
        ordinal=0,
        score=1.0,
    )


def test_corpus_toolbox_searches_domain_and_tracks_usage() -> None:
    index = FakeSearchIndex([hit("segment-1", "alpha beta")])
    toolbox = create_corpus_toolbox(
        index=index,  # type: ignore[arg-type]
        domain_id="domain-1",
        max_searches=2,
        max_citations=5,
        max_evidence_tokens=20,
    )

    result = toolbox.search_corpus("alpha", limit=4)

    assert index.calls == [("domain-1", "alpha", 4)]
    assert result["usage"] == {
        "search_count": 1,
        "citation_count": 1,
        "evidence_tokens": 2,
    }
    assert result["hits"][0]["segment_id"] == "segment-1"  # type: ignore[index]


def test_corpus_toolbox_enforces_search_and_evidence_budgets() -> None:
    index = FakeSearchIndex([hit("segment-1", "alpha beta gamma")])
    toolbox = create_corpus_toolbox(
        index=index,  # type: ignore[arg-type]
        domain_id="domain-1",
        max_searches=1,
        max_citations=5,
        max_evidence_tokens=1,
    )

    result = toolbox.search_corpus("alpha")

    assert result["hits"] == []
    with pytest.raises(CorpusToolError, match="search budget"):
        toolbox.search_corpus("alpha again")


def test_corpus_toolbox_reads_only_returned_citations() -> None:
    toolbox = create_corpus_toolbox(
        index=FakeSearchIndex([hit("segment-1", "alpha beta")]),  # type: ignore[arg-type]
        domain_id="domain-1",
        max_searches=1,
        max_citations=5,
        max_evidence_tokens=20,
    )

    toolbox.search_corpus("alpha")

    assert toolbox.read_citation("segment-1")["text"] == "alpha beta"
    with pytest.raises(CorpusToolError, match="not returned"):
        toolbox.read_citation("segment-2")
