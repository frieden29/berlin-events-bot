from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import Event
from .validation import InvalidEvent, build_event, value_at


@dataclass(slots=True)
class CollectionResult:
    events: list[Event]
    rejected: list[str]


class JsonApiSource:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def collect(self) -> CollectionResult:
        name = str(self.config["name"])
        endpoint = str(self.config["endpoint"])
        query = self.config.get("query", {})
        if query:
            endpoint = f"{endpoint}{'&' if '?' in endpoint else '?'}{urlencode(query)}"
        headers = {str(k): str(v) for k, v in self.config.get("request_headers", {}).items()}
        secret_name = self.config.get("api_key_env")
        if secret_name:
            secret = os.environ.get(str(secret_name))
            if not secret:
                raise RuntimeError(f"required environment variable is not set: {secret_name}")
            header = str(self.config.get("api_key_header", "Authorization"))
            headers[header] = f"{self.config.get('api_key_prefix', '')}{secret}"

        request = Request(endpoint, headers=headers, method="GET")
        with urlopen(request, timeout=30) as response:  # nosec: configured approved URL
            payload = json.load(response)
        records = value_at(payload, str(self.config.get("events_path", "events")))
        if not isinstance(records, list):
            raise RuntimeError(f"{name}: events_path did not resolve to a list")

        events: list[Event] = []
        rejected: list[str] = []
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                rejected.append(f"{name}[{index}]: record is not an object")
                continue
            try:
                events.append(build_event(name, record, self.config["fields"]))
            except InvalidEvent as exc:
                rejected.append(f"{name}[{index}]: {exc}")
        return CollectionResult(events, rejected)

