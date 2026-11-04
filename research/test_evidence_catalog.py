"""Policy checks for literature-to-app claims; do not interpret as clinical verification."""
import json
import unittest
from pathlib import Path
from urllib.parse import urlparse

CATALOG = json.loads((Path(__file__).parent / "evidence_catalog.json").read_text(encoding="utf8"))
ALLOWED_TIERS = {"core", "optional_exploratory", "research_only", "not_recommended"}

class EvidenceCatalogTests(unittest.TestCase):
    def test_unique_interventions(self):
        ids = [item["id"] for item in CATALOG["interventions"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_references_complete(self):
        refs = CATALOG["reference_urls"]
        for item in CATALOG["interventions"]:
            self.assertTrue(item["reference_ids"])
            for ref in item["reference_ids"]:
                self.assertIn(ref, refs)
                self.assertEqual(urlparse(refs[ref]).scheme, "https")

    def test_supported_tiers(self):
        for item in CATALOG["interventions"]:
            self.assertIn(item["tier"], ALLOWED_TIERS)
            self.assertTrue(item["evidence_summary"].strip())
            self.assertTrue(item["claim"].strip())

    def test_experimental_never_enabled(self):
        for item in CATALOG["interventions"]:
            if item["tier"] != "core":
                self.assertFalse(item["default_enabled"], item["id"])

    def test_only_20min_break_is_default(self):
        enabled = {item["id"] for item in CATALOG["interventions"] if item["default_enabled"]}
        self.assertEqual(enabled, {"distance_break_20"})

    def test_chromablur_is_research_only(self):
        items = {item["id"]: item for item in CATALOG["interventions"]}
        self.assertEqual(items["chromablur"]["tier"], "research_only")
        self.assertEqual(items["near_far_focus_switch"]["tier"], "optional_exploratory")
        self.assertEqual(items["blue_light_filter_for_strain"]["tier"], "not_recommended")

if __name__ == "__main__":
    unittest.main()
