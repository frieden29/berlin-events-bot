from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .deduplication import deduplicate
from .models import Event
from .sources import JsonApiSource


def load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        config = json.load(handle)
    if not isinstance(config.get("sources"), list):
        raise ValueError("config must contain a sources array")
    return config


def collect(config: dict[str, Any]) -> tuple[list[Event], list[str]]:
    events: list[Event] = []
    rejected: list[str] = []
    for source_config in config["sources"]:
        if not source_config.get("enabled", False):
            continue
        name = source_config.get("name", "unnamed source")
        if not source_config.get("terms_reviewed", False):
            raise ValueError(f"{name}: terms_reviewed must be true before enabling the source")
        if not source_config.get("terms_url") or not source_config.get("documentation_url"):
            raise ValueError(f"{name}: terms_url and documentation_url are required")
        result = JsonApiSource(source_config).collect()
        events.extend(result.events)
        rejected.extend(result.rejected)
    return deduplicate(events), rejected


def write_events(path: Path, events: list[Event]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(events),
        "events": [event.to_dict() for event in events],
    }
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
