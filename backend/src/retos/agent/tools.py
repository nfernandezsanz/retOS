from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from retos.search.index import SearchHit, SearchIndexMissingError, TantivySearchIndex


class CorpusToolError(RuntimeError):
    pass


def token_count(value: str) -> int:
    return len(value.split())


def hit_to_payload(hit: SearchHit) -> dict[str, object]:
    return {
        "segment_id": hit.segment_id,
        "document_id": hit.document_id,
        "document_version_id": hit.document_version_id,
        "title": hit.title,
        "anchor": hit.anchor,
        "ordinal": hit.ordinal,
        "score": hit.score,
        "text": hit.text,
        "token_count": token_count(hit.text),
    }


@dataclass
class CorpusToolbox:
    index: TantivySearchIndex
    domain_id: str
    max_searches: int
    max_citations: int
    max_evidence_tokens: int
    search_count: int = 0
    selected_hits: list[SearchHit] = field(default_factory=list)

    def usage_payload(self) -> dict[str, int]:
        return {
            "search_count": self.search_count,
            "citation_count": len(self.selected_hits),
            "evidence_tokens": sum(token_count(hit.text) for hit in self.selected_hits),
        }

    def search_corpus(self, query: str, limit: int | None = None) -> dict[str, object]:
        """Search indexed RetOS evidence for the current domain."""
        clean_query = query.strip()
        if not clean_query:
            raise CorpusToolError("query is required")
        if self.search_count >= self.max_searches:
            raise CorpusToolError("search budget exceeded")
        requested_limit = limit or self.max_citations
        if requested_limit < 1:
            raise CorpusToolError("limit must be positive")

        self.search_count += 1
        try:
            raw_hits = self.index.search_domain(
                self.domain_id,
                clean_query,
                limit=min(requested_limit, self.max_citations),
            )
        except SearchIndexMissingError as exc:
            raise CorpusToolError("Search index has not been built for this domain") from exc

        self.selected_hits = select_hits_within_evidence_budget(
            raw_hits,
            max_citations=self.max_citations,
            max_evidence_tokens=self.max_evidence_tokens,
        )
        return {
            "query": clean_query,
            "hits": [hit_to_payload(hit) for hit in self.selected_hits],
            "usage": self.usage_payload(),
        }

    def read_citation(self, segment_id: str) -> dict[str, object]:
        """Read a citation returned by search_corpus."""
        clean_segment_id = segment_id.strip()
        if not clean_segment_id:
            raise CorpusToolError("segment_id is required")
        for hit in self.selected_hits:
            if hit.segment_id == clean_segment_id:
                return hit_to_payload(hit)
        raise CorpusToolError("segment_id was not returned by search_corpus")

    def map_sources(self) -> dict[str, object]:
        """Group selected evidence by source document and anchor."""
        ensure_selected_hits(self.selected_hits)
        documents: dict[str, dict[str, Any]] = {}
        for hit in self.selected_hits:
            document = documents.setdefault(
                hit.document_id,
                {
                    "document_id": hit.document_id,
                    "document_version_id": hit.document_version_id,
                    "title": hit.title,
                    "anchors": [],
                    "segment_ids": [],
                    "evidence_tokens": 0,
                    "best_score": hit.score,
                },
            )
            document["segment_ids"].append(hit.segment_id)
            document["evidence_tokens"] += token_count(hit.text)
            document["best_score"] = max(float(document["best_score"]), hit.score)
            anchor_payload = {
                "segment_id": hit.segment_id,
                "anchor": hit.anchor,
                "ordinal": hit.ordinal,
                "score": hit.score,
                "token_count": token_count(hit.text),
            }
            document["anchors"].append(anchor_payload)
        return {
            "document_count": len(documents),
            "documents": sorted(
                documents.values(),
                key=lambda item: (-float(item["best_score"]), str(item["title"])),
            ),
            "usage": self.usage_payload(),
        }

    def inspect_evidence_table(self, segment_id: str | None = None) -> dict[str, object]:
        """Extract simple table and key-value rows from selected evidence."""
        ensure_selected_hits(self.selected_hits)
        hits = hits_for_optional_segment(self.selected_hits, segment_id)
        rows = []
        for hit in hits:
            rows.extend(table_rows_from_hit(hit))
        return {
            "row_count": len(rows),
            "rows": rows,
            "usage": self.usage_payload(),
        }


def select_hits_within_evidence_budget(
    hits: list[SearchHit],
    *,
    max_citations: int,
    max_evidence_tokens: int,
) -> list[SearchHit]:
    selected: list[SearchHit] = []
    evidence_tokens = 0
    for hit in hits[:max_citations]:
        next_tokens = token_count(hit.text)
        if selected and evidence_tokens + next_tokens > max_evidence_tokens:
            break
        if not selected and next_tokens > max_evidence_tokens:
            break
        selected.append(hit)
        evidence_tokens += next_tokens
    return selected


def ensure_selected_hits(hits: list[SearchHit]) -> None:
    if not hits:
        raise CorpusToolError("search_corpus must return evidence before this tool can run")


def hits_for_optional_segment(
    hits: list[SearchHit],
    segment_id: str | None,
) -> list[SearchHit]:
    if segment_id is None:
        return hits
    clean_segment_id = segment_id.strip()
    if not clean_segment_id:
        raise CorpusToolError("segment_id must not be blank")
    matching = [hit for hit in hits if hit.segment_id == clean_segment_id]
    if not matching:
        raise CorpusToolError("segment_id was not returned by search_corpus")
    return matching


def table_rows_from_hit(hit: SearchHit) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line_number, raw_line in enumerate(hit.text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        cells = split_table_line(line)
        if cells:
            rows.append(
                {
                    "segment_id": hit.segment_id,
                    "title": hit.title,
                    "anchor": hit.anchor,
                    "line_number": line_number,
                    "kind": "table_row",
                    "cells": cells,
                    "text": line,
                }
            )
            continue
        key_value = split_key_value_line(line)
        if key_value is not None:
            key, value = key_value
            rows.append(
                {
                    "segment_id": hit.segment_id,
                    "title": hit.title,
                    "anchor": hit.anchor,
                    "line_number": line_number,
                    "kind": "key_value",
                    "key": key,
                    "value": value,
                    "text": line,
                }
            )
    return rows


def split_table_line(line: str) -> list[str] | None:
    if "|" in line:
        cells = [cell.strip() for cell in line.strip("|").split("|") if cell.strip()]
    elif "\t" in line:
        cells = [cell.strip() for cell in line.split("\t") if cell.strip()]
    else:
        return None
    return cells if len(cells) >= 2 else None


def split_key_value_line(line: str) -> tuple[str, str] | None:
    for separator in (":", "="):
        if separator not in line:
            continue
        key, value = line.split(separator, 1)
        if key.strip() and value.strip():
            return key.strip(), value.strip()
    return None


def create_corpus_toolbox(
    *,
    index: TantivySearchIndex,
    domain_id: str,
    max_searches: int,
    max_citations: int,
    max_evidence_tokens: int,
) -> CorpusToolbox:
    return CorpusToolbox(
        index=index,
        domain_id=domain_id,
        max_searches=max_searches,
        max_citations=max_citations,
        max_evidence_tokens=max_evidence_tokens,
    )
