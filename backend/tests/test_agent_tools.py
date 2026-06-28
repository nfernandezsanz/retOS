import pytest

from retos.agent.tools import (
    CorpusToolError,
    clean_entity_candidate,
    create_corpus_toolbox,
    entity_candidates_from_source,
    hits_for_optional_segment,
    named_entity_followup_queries,
    split_table_line,
)
from retos.search.index import SearchHit


class FakeSearchIndex:
    def __init__(self, hits: list[SearchHit]) -> None:
        self.hits = hits
        self.calls: list[tuple[str, str, int]] = []

    def search_domain(self, domain_id: str, query_text: str, *, limit: int) -> list[SearchHit]:
        self.calls.append((domain_id, query_text, limit))
        return self.hits[:limit]


def hit(segment_id: str, text: str, *, title: str = "Fixture") -> SearchHit:
    return SearchHit(
        segment_id=segment_id,
        document_id="document-1",
        document_version_id="version-1",
        title=title,
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


def test_corpus_toolbox_accumulates_unique_hits_across_searches() -> None:
    class SwitchingSearchIndex(FakeSearchIndex):
        def search_domain(self, domain_id: str, query_text: str, *, limit: int) -> list[SearchHit]:
            self.calls.append((domain_id, query_text, limit))
            if query_text == "alpha":
                return [hit("segment-1", "alpha evidence")]
            return [hit("segment-2", "beta evidence"), hit("segment-1", "alpha evidence")]

    index = SwitchingSearchIndex([])
    toolbox = create_corpus_toolbox(
        index=index,  # type: ignore[arg-type]
        domain_id="domain-1",
        max_searches=2,
        max_citations=5,
        max_evidence_tokens=20,
    )

    first = toolbox.search_corpus("alpha")
    second = toolbox.search_corpus("beta")

    assert [item["segment_id"] for item in first["hits"]] == ["segment-1"]  # type: ignore[index]
    assert [item["segment_id"] for item in second["hits"]] == [  # type: ignore[index]
        "segment-1",
        "segment-2",
    ]
    assert second["usage"] == {
        "search_count": 2,
        "citation_count": 2,
        "evidence_tokens": 4,
    }


def test_corpus_toolbox_can_prioritize_followup_hits() -> None:
    class SwitchingSearchIndex(FakeSearchIndex):
        def search_domain(self, domain_id: str, query_text: str, *, limit: int) -> list[SearchHit]:
            self.calls.append((domain_id, query_text, limit))
            if query_text == "alpha":
                return [hit("segment-1", "alpha evidence"), hit("segment-2", "beta evidence")]
            return [hit("segment-3", "gamma evidence")]

    index = SwitchingSearchIndex([])
    toolbox = create_corpus_toolbox(
        index=index,  # type: ignore[arg-type]
        domain_id="domain-1",
        max_searches=2,
        max_citations=2,
        max_evidence_tokens=20,
    )

    toolbox.search_corpus("alpha")
    result = toolbox.search_corpus("gamma", prefer_new_hits=True)

    assert [item["segment_id"] for item in result["hits"]] == [  # type: ignore[index]
        "segment-3",
        "segment-1",
    ]


def test_named_entity_followup_queries_use_question_and_evidence_entities() -> None:
    queries = named_entity_followup_queries(
        question="Compare Animorphs and The Hork-Bajir Chronicles",
        hits=[
            hit(
                "segment-1",
                "Kiss and Tell starred Shirley Temple as Corliss Archer.",
            )
        ],
        max_queries=6,
    )

    assert "Animorphs" in queries
    assert "Hork-Bajir Chronicles" in queries
    assert "Shirley Temple" in queries


def test_named_entity_followup_queries_prioritize_new_evidence_entities() -> None:
    queries = named_entity_followup_queries(
        question=(
            "The football manager who recruited David Beckham managed Manchester United "
            "during what timeframe?"
        ),
        hits=[
            hit(
                "segment-1",
                "The David Beckham Academy was a football school founded by David Beckham.",
                title="HotpotQA: David Beckham Academy",
            ),
            hit(
                "segment-2",
                (
                    "The 1995-96 season was Manchester United's fourth season. "
                    "Their triumph was remarkable because Alex Ferguson had sold "
                    "experienced players before the start of the season."
                ),
                title="HotpotQA: 1995-96 Manchester United F.C. season",
            ),
        ],
        max_queries=8,
    )

    assert "Alex Ferguson" in queries
    assert queries.index("Alex Ferguson") < queries.index("David Beckham")


def test_named_entity_followup_queries_extract_administration_bridge() -> None:
    queries = named_entity_followup_queries(
        question=(
            "Roger O. Egeberg was Assistant Secretary for Health and Scientific Affairs "
            "during the administration of a president that served during what years?"
        ),
        hits=[
            hit(
                "segment-1",
                (
                    "Roger Olaf Egeberg served as Assistant Secretary for Health and "
                    "Scientific Affairs during the Nixon administration."
                ),
                title="HotpotQA: Roger O. Egeberg",
            )
        ],
        max_queries=6,
    )

    assert "Nixon administration" in queries


def test_named_entity_followup_queries_keep_comparison_entities_near_front() -> None:
    queries = named_entity_followup_queries(
        question=(
            "Which performance act has a higher instrument to person ratio, "
            "Badly Drawn Boy or Wolf Alice?"
        ),
        hits=[
            hit(
                "segment-1",
                "Wolf Alice are a four-piece alternative rock band from North London.",
                title="HotpotQA: Wolf Alice",
            ),
            hit(
                "segment-2",
                "Something to Talk About is a song by British musical artist Badly Drawn Boy.",
                title="HotpotQA: Something to Talk About (Badly Drawn Boy song)",
            ),
            hit(
                "segment-3",
                "Tom Rothrock has worked with many artists.",
                title="HotpotQA: Tom Rothrock",
            ),
        ],
        max_queries=8,
    )

    assert "Badly Drawn Boy" in queries
    assert "Wolf Alice" in queries


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


def test_corpus_toolbox_rejects_invalid_search_inputs() -> None:
    toolbox = create_corpus_toolbox(
        index=FakeSearchIndex([hit("segment-1", "alpha beta")]),  # type: ignore[arg-type]
        domain_id="domain-1",
        max_searches=1,
        max_citations=5,
        max_evidence_tokens=20,
    )

    with pytest.raises(CorpusToolError, match="query is required"):
        toolbox.search_corpus("   ")
    with pytest.raises(CorpusToolError, match="limit must be positive"):
        toolbox.search_corpus("alpha", limit=-1)


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
    with pytest.raises(CorpusToolError, match="segment_id is required"):
        toolbox.read_citation(" ")
    with pytest.raises(CorpusToolError, match="not returned"):
        toolbox.read_citation("segment-2")


def test_corpus_toolbox_maps_selected_sources() -> None:
    toolbox = create_corpus_toolbox(
        index=FakeSearchIndex(
            [
                hit("segment-1", "alpha beta"),
                SearchHit(
                    segment_id="segment-2",
                    document_id="document-2",
                    document_version_id="version-2",
                    title="Second",
                    text="gamma delta epsilon",
                    anchor="page=2",
                    ordinal=4,
                    score=3.0,
                ),
            ]
        ),  # type: ignore[arg-type]
        domain_id="domain-1",
        max_searches=1,
        max_citations=5,
        max_evidence_tokens=20,
    )

    toolbox.search_corpus("alpha")
    result = toolbox.map_sources()

    assert result["document_count"] == 2
    documents = result["documents"]
    assert documents[0]["document_id"] == "document-2"  # type: ignore[index]
    assert documents[0]["anchors"] == [  # type: ignore[index]
        {
            "segment_id": "segment-2",
            "anchor": "page=2",
            "ordinal": 4,
            "score": 3.0,
            "token_count": 3,
        }
    ]
    assert result["usage"] == {
        "search_count": 1,
        "citation_count": 2,
        "evidence_tokens": 5,
    }


def test_corpus_toolbox_inspects_table_and_key_value_rows() -> None:
    table_hit = hit(
        "segment-table",
        "Metric | Value\nTotal: 42\nIgnored plain sentence\nOwner = Research",
    )
    toolbox = create_corpus_toolbox(
        index=FakeSearchIndex([table_hit]),  # type: ignore[arg-type]
        domain_id="domain-1",
        max_searches=1,
        max_citations=5,
        max_evidence_tokens=20,
    )

    toolbox.search_corpus("total")
    result = toolbox.inspect_evidence_table("segment-table")

    assert result["row_count"] == 3
    assert result["rows"] == [
        {
            "segment_id": "segment-table",
            "title": "Fixture",
            "anchor": "page=1",
            "line_number": 1,
            "kind": "table_row",
            "cells": ["Metric", "Value"],
            "text": "Metric | Value",
        },
        {
            "segment_id": "segment-table",
            "title": "Fixture",
            "anchor": "page=1",
            "line_number": 2,
            "kind": "key_value",
            "key": "Total",
            "value": "42",
            "text": "Total: 42",
        },
        {
            "segment_id": "segment-table",
            "title": "Fixture",
            "anchor": "page=1",
            "line_number": 4,
            "kind": "key_value",
            "key": "Owner",
            "value": "Research",
            "text": "Owner = Research",
        },
    ]


def test_corpus_toolbox_inspects_all_selected_table_rows_when_segment_is_omitted() -> None:
    toolbox = create_corpus_toolbox(
        index=FakeSearchIndex(
            [
                hit("segment-table", "Metric\tValue"),
                hit("segment-key", "Owner: Research"),
            ]
        ),  # type: ignore[arg-type]
        domain_id="domain-1",
        max_searches=1,
        max_citations=5,
        max_evidence_tokens=20,
    )

    toolbox.search_corpus("metadata")
    result = toolbox.inspect_evidence_table()

    assert result["row_count"] == 2
    assert result["rows"][0]["cells"] == ["Metric", "Value"]  # type: ignore[index]
    assert result["rows"][1]["key"] == "Owner"  # type: ignore[index]


def test_corpus_toolbox_source_tools_require_selected_evidence() -> None:
    toolbox = create_corpus_toolbox(
        index=FakeSearchIndex([hit("segment-1", "alpha beta")]),  # type: ignore[arg-type]
        domain_id="domain-1",
        max_searches=1,
        max_citations=5,
        max_evidence_tokens=20,
    )

    with pytest.raises(CorpusToolError, match="search_corpus"):
        toolbox.map_sources()
    with pytest.raises(CorpusToolError, match="search_corpus"):
        toolbox.inspect_evidence_table()
    toolbox.search_corpus("alpha")
    with pytest.raises(CorpusToolError, match="segment_id"):
        toolbox.inspect_evidence_table(" ")
    with pytest.raises(CorpusToolError, match="not returned"):
        toolbox.inspect_evidence_table("missing")


def test_hits_for_optional_segment_returns_all_or_single_match() -> None:
    hits = [hit("segment-1", "alpha beta"), hit("segment-2", "gamma delta")]

    assert hits_for_optional_segment(hits, None) == hits
    assert [item.segment_id for item in hits_for_optional_segment(hits, "segment-2")] == [
        "segment-2"
    ]
    with pytest.raises(CorpusToolError, match="must not be blank"):
        hits_for_optional_segment(hits, " ")


def test_entity_candidate_cleaning_rejects_stopwords_and_short_tokens() -> None:
    assert clean_entity_candidate("Compare The Apollo Program") == "Apollo Program"
    assert clean_entity_candidate("The") == ""
    assert clean_entity_candidate("AI") == ""
    assert entity_candidates_from_source("The and Of") == []


def test_entity_candidate_variants_split_comparisons() -> None:
    candidates = entity_candidates_from_source("Compare Apollo Program and The Gemini Program")

    assert "Apollo Program" in candidates
    assert "Gemini" in candidates
    assert "Apollo Program and The Gemini" in candidates


def test_split_table_line_rejects_single_cell_lines() -> None:
    assert split_table_line("| only-one |") is None
    assert split_table_line("plain line") is None
