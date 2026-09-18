from __future__ import annotations

import re
import unicodedata
from datetime import timezone

from .models import Event, SourceRef


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^\w]+", " ", value).strip()


def _cross_source_key(event: Event) -> tuple[str, str, str]:
    instant = event.parsed_start.astimezone(timezone.utc).isoformat()
    place = " | ".join(filter(None, (_normalize(event.venue), _normalize(event.address))))
    return _normalize(event.title), instant, place


def deduplicate(events: list[Event]) -> list[Event]:
    results: list[Event] = []
    by_source: dict[tuple[str, str], Event] = {}
    by_details: dict[tuple[str, str, str], Event] = {}

    for event in events:
        source_key = (_normalize(event.source), event.source_id)
        details_key = _cross_source_key(event)
        existing = by_source.get(source_key) or by_details.get(details_key)
        if existing is None:
            results.append(event)
            by_source[source_key] = event
            by_details[details_key] = event
            continue
        ref = SourceRef(event.source, event.source_id)
        if ref not in existing.source_refs:
            existing.source_refs.append(ref)
        for attr in ("end", "url", "description", "venue", "address"):
            if not getattr(existing, attr) and getattr(event, attr):
                setattr(existing, attr, getattr(event, attr))
        by_source[source_key] = existing
        by_details[details_key] = existing

    return sorted(results, key=lambda event: event.parsed_start)

