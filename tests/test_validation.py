import unittest

from berlin_events.validation import InvalidEvent, build_event


FIELDS = {
    "source_id": "id",
    "title": "title",
    "start": "start",
    "end": "end",
    "venue": "place.name",
    "address": "place.address",
    "city": "place.city",
    "url": "url",
    "description": "description",
}


def valid_record(**changes):
    record = {
        "id": "event-1",
        "title": "Berlin Test Event",
        "start": "2026-10-01T18:30:00+02:00",
        "place": {"name": "Test Hall", "address": "Teststraße 1", "city": "Berlin"},
    }
    record.update(changes)
    return record


class ValidationTests(unittest.TestCase):
    def test_accepts_complete_berlin_event(self):
        event = build_event("test", valid_record(), FIELDS)
        self.assertEqual(event.source_id, "event-1")
        self.assertEqual(event.city, "Berlin")

    def test_rejects_missing_time(self):
        with self.assertRaisesRegex(InvalidEvent, "time is required"):
            build_event("test", valid_record(start="2026-10-01"), FIELDS)

    def test_rejects_naive_time(self):
        with self.assertRaisesRegex(InvalidEvent, "UTC offset"):
            build_event("test", valid_record(start="2026-10-01T18:30:00"), FIELDS)

    def test_rejects_missing_place(self):
        with self.assertRaisesRegex(InvalidEvent, "missing place"):
            build_event("test", valid_record(place={"city": "Berlin"}), FIELDS)

    def test_rejects_non_berlin_event(self):
        with self.assertRaisesRegex(InvalidEvent, "not in Berlin"):
            build_event("test", valid_record(place={"name": "Hall", "city": "Potsdam"}), FIELDS)

    def test_rejects_missing_source_id(self):
        with self.assertRaisesRegex(InvalidEvent, "source_id"):
            build_event("test", valid_record(id=""), FIELDS)


if __name__ == "__main__":
    unittest.main()

