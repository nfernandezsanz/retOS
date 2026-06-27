from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

SourceKind = Literal["upload", "mount", "url"]


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Domain:
    id: str
    slug: str
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class Source:
    id: str
    domain_id: str
    kind: SourceKind
    name: str
    uri: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class Document:
    id: str
    domain_id: str
    source_id: str | None
    external_id: str | None
    title: str
    content_hash: str
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class DocumentVersion:
    id: str
    document_id: str
    version: int
    source_uri: str
    content_hash: str
    size_bytes: int
    created_at: datetime


@dataclass(frozen=True)
class Artifact:
    id: str
    document_version_id: str
    kind: str
    uri: str
    sha256: str
    size_bytes: int
    created_at: datetime


@dataclass(frozen=True)
class Segment:
    id: str
    document_version_id: str
    ordinal: int
    text: str
    anchor: str | None
    token_count: int
    content_hash: str
    created_at: datetime
