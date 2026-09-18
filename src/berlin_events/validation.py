from __future__ import annotations

from datetime import datetime
from typing import Any

from .models import Event, SourceRef


class InvalidEvent(ValueError):
    """Raised when a source record cannot produce a complete Berlin event."""


def _required_text(value: Any, name: str) -> str:
    if value is None or not str(value).strip():
        raise InvalidEvent(f"missing {name}")
    return str(value).strip()


def _optional_text(value: Any) -> str | None:
    return str(value).strip() if value is not None and str(value).strip() else None


def _iso_datetime(value: Any, name: str) -> str:
    text = _required_text(value, name)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidEvent(f"invalid {name}: expected ISO 8601") from exc
    if "T" not in text and " " not in text:
        raise InvalidEvent(f"invalid {name}: time is required")
    if parsed.tzinfo is None:
        raise InvalidEvent(f"invalid {name}: UTC offset is required")
    return text


def build_event(source: str, record: dict[str, Any], fields: dict[str, str]) -> Event:
    values = {name: value_at(record, path) for name, path in fields.items()}
    venue = _optional_text(values.get("venue")) or ""
    address = _optional_text(values.get("address")) or ""
    if not venue and not address:
        raise InvalidEvent("missing place: venue or address is required")
    city = _required_text(values.get("city"), "city")
    if city.casefold() != "berlin":
        raise InvalidEvent("event is not in Berlin")

    source_id = _required_text(values.get("source_id"), "source_id")
    event = Event(
        source=_required_text(source, "source"),
        source_id=source_id,
        title=_required_text(values.get("title"), "title"),
        start=_iso_datetime(values.get("start"), "start"),
        end=_iso_datetime(values["end"], "end") if values.get("end") else None,
        venue=venue,
        address=address,
        city="Berlin",
        url=_optional_text(values.get("url")),
        description=_optional_text(values.get("description")),
        source_refs=[SourceRef(source=source, source_id=source_id)],
    )
    if event.end and datetime.fromisoformat(event.end.replace("Z", "+00:00")) < event.parsed_start:
        raise InvalidEvent("end is before start")
    return event


def value_at(record: dict[str, Any], dotted_path: str) -> Any:
    value: Any = record
    for part in dotted_path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value

