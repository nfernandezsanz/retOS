from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

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
