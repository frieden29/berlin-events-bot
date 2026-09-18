"""Synthetic fixtures only; network is mocked in every collector test."""
import copy
import io
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from berlin_events.pipeline import collect, load_config
from berlin_events.ticketmaster import TicketmasterSource, parse_event

FIXTURE = {
    "id": "synthetic-1", "name": "Synthetic test event", "url": "https://example.invalid/event",
    "dates": {"timezone": "Europe/Berlin", "start": {
        "dateTime": "2026-07-01T22:30:00Z", "localDate": "2026-07-02", "localTime": "00:30:00"}},
    "_embedded": {"venues": [{"name": "Synthetic venue", "address": {"line1": "Synthetic street 1"},
        "city": {"name": "Berlin"}, "country": {"countryCode": "DE"},
        "location": {"latitude": "52.5", "longitude": "13.4"}}]},
}

def response(records, page=0, pages=1, available="4999"):
    stream = io.StringIO(json.dumps({"page": {"number": page, "totalPages": pages,
        "totalElements": len(records)}, "_embedded": {"events": records}}))
    stream.headers = {"Rate-Limit-Available": available}
    return stream

class TicketmasterTests(unittest.TestCase):
    def setUp(self):
        self.record = copy.deepcopy(FIXTURE)
        self.config = load_config(Path(__file__).parents[1] / "config/sources.json")
        self.source = TicketmasterSource(self.config["sources"][0])
        for target in (patch.dict(os.environ, {"BERLIN_EVENTS_API_KEY": "synthetic-test-credential"}),):
            target.start()
            self.addCleanup(target.stop)
        network = patch("berlin_events.ticketmaster.build_opener")
        self.opener = network.start().return_value
        self.addCleanup(network.stop)
        sleeper = patch("berlin_events.ticketmaster.time.sleep")
        self.sleep = sleeper.start()
        self.addCleanup(sleeper.stop)

    def test_summer_midnight_and_coordinates(self):
        event = parse_event(self.record)
        self.assertEqual(event.start, "2026-07-02T00:30:00+02:00")
        self.assertEqual((event.latitude, event.longitude), (52.5, 13.4))
        self.assertEqual(event.url, FIXTURE["url"])

    def test_winter_offset(self):
        self.record["dates"]["start"] = {"dateTime": "2026-12-01T23:30:00Z"}
        self.assertEqual(parse_event(self.record).start, "2026-12-02T00:30:00+01:00")

    def test_date_only_datetime_rejected(self):
        self.record["dates"]["start"] = {"dateTime": "2026-07-02+02:00"}
        with self.assertRaises(ValueError):
            parse_event(self.record)

    def test_five_page_boundary(self):
        self.opener.open.side_effect = [response([FIXTURE], page=i, pages=5) for i in range(5)]
        self.assertEqual(len(self.source.collect().events), 5)
        self.assertEqual(self.opener.open.call_count, 5)
        self.assertEqual(self.sleep.call_count, 4)

    def test_malformed_page_fails(self):
        stream = io.StringIO('{}')
        stream.headers = {}
        self.opener.open.return_value = stream
        with self.assertRaisesRegex(RuntimeError, "invalid page"):
            self.source.collect()

    def test_local_time_fallback(self):
        del self.record["dates"]["start"]["dateTime"]
        self.assertEqual(parse_event(self.record).start, "2026-07-02T00:30:00+02:00")

    def test_rejects_dst_gap_and_ambiguity(self):
        for day in ("2026-03-29", "2026-10-25"):
            self.record["dates"]["start"] = {"localDate": day, "localTime": "02:30:00"}
            with self.subTest(day=day), self.assertRaises(ValueError):
                parse_event(self.record)

    def test_rejects_missing_time_or_date(self):
        for start in ({"localDate": "2026-07-02"}, {"localTime": "12:00:00"}, {}):
            self.record["dates"]["start"] = start
            with self.subTest(start=start), self.assertRaises(ValueError):
                parse_event(self.record)

    def test_rejects_uncertain_flags(self):
        for flag in ("dateTBA", "dateTBD", "timeTBA", "noSpecificTime"):
            record = copy.deepcopy(FIXTURE)
            record["dates"]["start"][flag] = True
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                parse_event(record)

    def test_rejects_missing_place(self):
        self.record["_embedded"]["venues"] = []
        with self.assertRaises(ValueError):
            parse_event(self.record)

    def test_rejects_other_city_or_country(self):
        for field, value in (("city", {"name": "Potsdam"}), ("country", {"countryCode": "US"})):
            record = copy.deepcopy(FIXTURE)
            record["_embedded"]["venues"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                parse_event(record)

    def test_rejects_conflicting_local_date(self):
        self.record["dates"]["start"]["localDate"] = "2026-07-01"
        with self.assertRaises(ValueError):
            parse_event(self.record)

    def test_invalid_coordinates_not_invented(self):
        self.record["_embedded"]["venues"][0]["location"]["latitude"] = "NaN"
        self.assertIsNone(parse_event(self.record).latitude)

    def test_auth_filters_and_pipeline_dedup(self):
        other = copy.deepcopy(FIXTURE)
        other["id"] = "synthetic-2"
        self.opener.open.return_value = response([FIXTURE, FIXTURE, other])
        events, rejected = collect(self.config)
        self.assertEqual((len(events), rejected), (1, []))
        request = self.opener.open.call_args.args[0]
        query = parse_qs(urlsplit(request.full_url).query)
        self.assertEqual(query["apikey"], ["synthetic-test-credential"])
        self.assertEqual(query["city"], ["Berlin"])
        self.assertEqual(query["countryCode"], ["DE"])
        self.assertIsNone(request.get_header("Authorization"))
        self.assertNotIn("synthetic-test-credential", json.dumps(events[0].to_dict()))

    def test_pagination_pacing(self):
        self.opener.open.side_effect = [response([FIXTURE], pages=2), response([FIXTURE], page=1, pages=2)]
        self.assertEqual(len(self.source.collect().events), 2)
        self.sleep.assert_called_once_with(1)

    def test_empty_response(self):
        self.opener.open.return_value = response([], pages=0)
        self.assertEqual(self.source.collect().events, [])

    def test_deep_paging_fails(self):
        self.opener.open.return_value = response([FIXTURE], pages=6)
        with self.assertRaisesRegex(RuntimeError, "1000-event"):
            self.source.collect()
        self.assertEqual(self.opener.open.call_count, 1)

    def test_http_error_no_retry_or_secret(self):
        for status in (401, 429, 500):
            self.opener.open.reset_mock()
            self.opener.open.side_effect = HTTPError("https://example.invalid/?apikey=synthetic-test-credential",
                status, "synthetic-test-credential", {}, None)
            with self.subTest(status=status), self.assertRaises(RuntimeError) as caught:
                self.source.collect()
            self.assertNotIn("synthetic-test-credential", str(caught.exception))
            self.assertEqual(self.opener.open.call_count, 1)

    def test_network_error_sanitized(self):
        self.opener.open.side_effect = OSError("synthetic-test-credential")
        with self.assertRaises(RuntimeError) as caught:
            self.source.collect()
        self.assertNotIn("synthetic-test-credential", str(caught.exception))

    def test_exhausted_quota_stops(self):
        self.opener.open.return_value = response([FIXTURE], pages=2, available="0")
        with self.assertRaisesRegex(RuntimeError, "quota exhausted"):
            self.source.collect()
        self.assertEqual(self.opener.open.call_count, 1)

    def test_echoed_secret_and_malformed_record(self):
        self.record["name"] = "synthetic-test-credential"
        self.opener.open.return_value = response([self.record, None, FIXTURE])
        result = self.source.collect()
        self.assertEqual((len(result.events), len(result.rejected)), (1, 2))
        self.assertNotIn("synthetic-test-credential", str(result.rejected))

    def test_missing_key_no_network(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(RuntimeError):
            self.source.collect()
        self.opener.open.assert_not_called()

    def test_wrong_host_no_network(self):
        self.source.config["endpoint"] = "https://example.invalid"
        with self.assertRaises(RuntimeError):
            self.source.collect()
        self.opener.open.assert_not_called()
