from __future__ import annotations

from dataclasses import dataclass, field

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
