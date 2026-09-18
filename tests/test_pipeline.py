import json
import tempfile
import unittest
from pathlib import Path

from berlin_events.pipeline import collect, load_config, write_events


class PipelineTests(unittest.TestCase):
    def test_default_config_collects_no_fabricated_events(self):
        config = load_config(Path(__file__).parents[1] / "config" / "sources.json")
        events, rejected = collect(config)
        self.assertEqual(events, [])
        self.assertEqual(rejected, [])

    def test_output_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "events.json"
            write_events(output, [])
            document = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(document["count"], 0)
        self.assertEqual(document["events"], [])
        self.assertIsNotNone(document["generated_at"])

    def test_enabled_source_requires_terms_review(self):
        config = {"sources": [{"name": "unreviewed", "enabled": True}]}
        with self.assertRaisesRegex(ValueError, "terms_reviewed"):
            collect(config)


if __name__ == "__main__":
    unittest.main()
