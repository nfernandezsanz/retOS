from __future__ import annotations

import re
import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import tantivy


@dataclass(frozen=True)
class IndexedSegment:
    segment_id: str
    document_id: str
    document_version_id: str
    title: str
    text: str
    anchor: str | None
    ordinal: int


@dataclass(frozen=True)
class SearchHit:
    segment_id: str
    document_id: str
    document_version_id: str
    title: str
    text: str
    anchor: str | None
    ordinal: int
    score: float


class SearchIndexMissingError(RuntimeError):
    pass


def natural_language_query_text(query_text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", query_text).split())


def domain_index_path(index_root: str | Path, domain_id: str) -> Path:
    return Path(index_root) / "domains" / domain_id / "tantivy"


def build_schema() -> tantivy.Schema:
    builder = tantivy.SchemaBuilder()
    builder.add_text_field("segment_id", stored=True)
    builder.add_text_field("document_id", stored=True)
    builder.add_text_field("document_version_id", stored=True)
    builder.add_text_field("title", stored=True)
    builder.add_text_field("body", stored=True)
    builder.add_text_field("anchor", stored=True)
    builder.add_integer_field("ordinal", stored=True)
    return builder.build()


class TantivySearchIndex:
    def __init__(self, index_root: str | Path) -> None:
        self._index_root = Path(index_root)
        self._schema = build_schema()

    def rebuild_domain(self, domain_id: str, segments: Iterable[IndexedSegment]) -> int:
        path = domain_index_path(self._index_root, domain_id)
        tmp_path = path.with_name(f"{path.name}.tmp")
        if tmp_path.exists():
            shutil.rmtree(tmp_path)
        tmp_path.mkdir(parents=True)

        index = tantivy.Index(self._schema, path=str(tmp_path))
        writer = index.writer()
        count = 0
        for segment in segments:
            writer.add_document(
                tantivy.Document(
                    segment_id=segment.segment_id,
                    document_id=segment.document_id,
                    document_version_id=segment.document_version_id,
                    title=segment.title,
                    body=segment.text,
                    anchor=segment.anchor or "",
                    ordinal=segment.ordinal,
                )
            )
            count += 1
        writer.commit()

        if path.exists():
            shutil.rmtree(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.replace(path)
        return count

    def search_domain(self, domain_id: str, query_text: str, *, limit: int = 10) -> list[SearchHit]:
        path = domain_index_path(self._index_root, domain_id)
        if not path.exists():
            raise SearchIndexMissingError("Search index has not been built for this domain")

        index = tantivy.Index.open(str(path))
        index.reload()
        try:
            query = index.parse_query(query_text, ["title", "body"])
        except ValueError:
            fallback_query_text = natural_language_query_text(query_text)
            if not fallback_query_text:
                return []
            query = index.parse_query(fallback_query_text, ["title", "body"])
        searcher = index.searcher()
        results = searcher.search(query, limit)
        hits: list[SearchHit] = []
        for score, address in results.hits:
            doc = searcher.doc(address)
            hits.append(
                SearchHit(
                    segment_id=str(doc["segment_id"][0]),
                    document_id=str(doc["document_id"][0]),
                    document_version_id=str(doc["document_version_id"][0]),
                    title=str(doc["title"][0]),
                    text=str(doc["body"][0]),
                    anchor=str(doc["anchor"][0]) or None,
                    ordinal=int(doc["ordinal"][0]),
                    score=float(score),
                )
            )
        return hits
