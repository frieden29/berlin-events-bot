from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class SourceRef:
    source: str
    source_id: str


@dataclass(slots=True)
class Event:
    source: str
    source_id: str
    title: str
    start: str
    venue: str
    address: str
    city: str = "Berlin"
    end: str | None = None
    url: str | None = None
    description: str | None = None
    source_refs: list[SourceRef] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["source_refs"] = [asdict(ref) for ref in self.source_refs]
        return value

    @property
    def parsed_start(self) -> datetime:
        return datetime.fromisoformat(self.start.replace("Z", "+00:00"))

