"""Ticketmaster Discovery v2; never log credential-bearing URLs or response bodies."""
import json
import math
import os
import re
import time
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo

from .sources import CollectionResult
from .validation import InvalidEvent, build_event

ENDPOINT = "https://app.ticketmaster.com/discovery/v2/events.json"
BERLIN = ZoneInfo("Europe/Berlin")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def start_time(record):
    dates = record.get("dates", {})
    start = dates.get("start", {})
    if any(start.get(flag) for flag in ("dateTBA", "dateTBD", "timeTBA", "noSpecificTime")):
        raise InvalidEvent("unconfirmed date or time")
    if dates.get("status", {}).get("code") in ("cancelled", "postponed"):
        raise InvalidEvent("cancelled or postponed")
    if start.get("dateTime"):
        if not isinstance(start["dateTime"], str) or not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", start["dateTime"]):
            raise InvalidEvent("explicit datetime required")
        instant = datetime.fromisoformat(start["dateTime"].replace("Z", "+00:00"))
        if instant.tzinfo is None:
            raise InvalidEvent("dateTime must have an offset")
        local = instant.astimezone(BERLIN)
        if start.get("localDate") and start["localDate"] != local.date().isoformat():
            raise InvalidEvent("conflicting local date")
        if start.get("localTime") and start["localTime"] != local.strftime("%H:%M:%S"):
            raise InvalidEvent("conflicting local time")
        return local.isoformat()
    day, clock = start.get("localDate"), start.get("localTime")
    if not day or not clock or dates.get("timezone") != "Europe/Berlin":
        raise InvalidEvent("missing explicit local date, time or timezone")
    if not isinstance(day, str) or not isinstance(clock, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) or not re.fullmatch(r"\d{2}:\d{2}:\d{2}", clock):
        raise InvalidEvent("invalid local date or time format")
    naive = datetime.fromisoformat(f"{day}T{clock}")
    if naive.tzinfo is not None:
        raise InvalidEvent("unexpected offset in local time")
    candidates = set()
    for fold in (0, 1):
        aware = naive.replace(tzinfo=BERLIN, fold=fold)
        utc = aware.astimezone(timezone.utc)
        if utc.astimezone(BERLIN).replace(tzinfo=None) == naive:
            candidates.add(utc)
    if len(candidates) != 1:
        raise InvalidEvent("ambiguous or nonexistent daylight-saving time")
    return candidates.pop().astimezone(BERLIN).isoformat()


def parse_event(record):
    venues = record.get("_embedded", {}).get("venues", [])
    if not isinstance(venues, list) or len(venues) != 1:
        raise InvalidEvent("missing or ambiguous venue")
    venue = venues[0]
    if venue.get("country", {}).get("countryCode") != "DE":
        raise InvalidEvent("venue must be in Germany")
    for text in (record.get("id"), record.get("name")):
        if not isinstance(text, str) or not text.strip():
            raise InvalidEvent("missing ID or title")
    address = venue.get("address", {})
    if venue.get("name") is not None and not isinstance(venue["name"], str):
        raise InvalidEvent("venue name must be text")
    lines = [address.get(key) for key in ("line1", "line2", "line3")]
    normalized = {
        "source_id": record["id"], "title": record["name"],
        "start": start_time(record), "venue": venue.get("name"),
        "address": ", ".join(line for line in lines if isinstance(line, str) and line.strip()),
        "city": venue.get("city", {}).get("name"), "url": record.get("url"),
    }
    event = build_event("ticketmaster", normalized, {key: key for key in normalized})
    location = venue.get("location", {})
    try:
        lat, lon = float(location["latitude"]), float(location["longitude"])
        if math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180:
            event.latitude, event.longitude = lat, lon
    except (KeyError, TypeError, ValueError):
        pass
    return event


class TicketmasterSource:
    def __init__(self, config):
        self.config = config

    def collect(self):
        if self.config.get("endpoint") != ENDPOINT:
            raise RuntimeError("Ticketmaster endpoint must be the approved HTTPS endpoint")
        secret = os.environ.get(self.config.get("api_key_env", "BERLIN_EVENTS_API_KEY"))
        if not secret:
            raise RuntimeError("Ticketmaster API environment variable is missing")
        query = dict(self.config.get("query", {}))
        query.update(city="Berlin", countryCode="DE", size=200, includeTBA="no", includeTBD="no", includeTest="no")
        opener = build_opener(NoRedirect())
        events, rejected = [], []
        for page in range(5):  # 0..4 => size * page < 1000
            if page:
                time.sleep(1)
            query.update(page=page, apikey=secret)
            request = Request(ENDPOINT + "?" + urlencode(query), headers={
                "Accept": "application/json", "User-Agent": "Berlin-Events-Bot/0.1"
            })
            try:
                with opener.open(request, timeout=30) as response:
                    payload = json.load(response)
                    available = response.headers.get("Rate-Limit-Available")
            except HTTPError as exc:
                raise RuntimeError(f"Ticketmaster HTTP {exc.code}; collection stopped, no retry") from None
            except Exception:
                raise RuntimeError("Ticketmaster request or JSON decoding failed") from None
            try:
                metadata = payload["page"]
                total = metadata["totalPages"]
                if not isinstance(total, int) or total < 0 or metadata["number"] != page:
                    raise ValueError
                if total > 5:
                    raise RuntimeError("Ticketmaster exceeds the 1000-event window; narrow the date range before retrying")
                records = payload.get("_embedded", {}).get("events", [])
                if not isinstance(records, list) or (not records and metadata.get("totalElements", 0) != 0):
                    raise ValueError
            except (KeyError, TypeError, ValueError, AttributeError):
                raise RuntimeError("Ticketmaster response has an invalid page structure") from None
            for index, record in enumerate(records):
                # Never include raw records, exception strings or URLs in diagnostics.
                try:
                    serialized = json.dumps(record, ensure_ascii=False)
                    if secret in serialized:
                        raise InvalidEvent("credential echoed in record")
                    events.append(parse_event(record))
                except (InvalidEvent, ValueError, TypeError, KeyError, AttributeError):
                    rejected.append(f"ticketmaster page {page} record {index}: invalid or incomplete event")
            if page + 1 >= total:
                return CollectionResult(events, rejected)
            if available is not None and (not str(available).isdigit() or int(available) <= 0):
                raise RuntimeError("Ticketmaster quota exhausted; collection stopped, no retry")
        raise RuntimeError("Ticketmaster pagination limit reached")
