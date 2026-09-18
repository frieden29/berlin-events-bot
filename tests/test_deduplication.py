import unittest

from berlin_events.deduplication import deduplicate
from berlin_events.models import Event, SourceRef


def event(source="api-a", source_id="1", title="Jazz Night", start="2026-10-01T20:00:00+02:00"):
    return Event(
        source=source,
        source_id=source_id,
        title=title,
        start=start,
        venue="Music Hall",
        address="Alexanderplatz 1",
        city="Berlin",
        source_refs=[SourceRef(source, source_id)],
    )


class DeduplicationTests(unittest.TestCase):
    def test_same_source_id_is_duplicate(self):
        self.assertEqual(len(deduplicate([event(), event(title="Changed title")])), 1)

    def test_cross_source_details_are_duplicate(self):
        result = deduplicate([event(), event(source="api-b", source_id="99", title="JAZZ night")])
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0].source_refs), 2)

    def test_same_title_different_time_is_not_duplicate(self):
        result = deduplicate([event(), event(source="api-b", start="2026-10-01T21:00:00+02:00")])
        self.assertEqual(len(result), 2)

    def test_equivalent_instants_are_duplicate(self):
        result = deduplicate([event(), event(source="api-b", start="2026-10-01T18:00:00Z")])
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()

