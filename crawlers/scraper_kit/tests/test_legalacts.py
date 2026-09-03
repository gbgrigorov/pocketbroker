"""Parser tests for legalacts results, against a captured Артекс fixture.

    python3 -m unittest crawlers.scraper_kit.tests.test_legalacts
"""
import unittest
from pathlib import Path

from crawlers.scraper_kit.sites.legalacts import parse_results

FIXTURE = Path(__file__).parent / "fixtures" / "legalacts_results_artex.html"


class ParseResultsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = parse_results(FIXTURE.read_text(encoding="utf-8"))

    def test_finds_all_acts(self):
        self.assertEqual(len(self.rows), 14)

    def test_first_row_shape(self):
        r = self.rows[0]
        self.assertTrue(r["url"].startswith("https://legalacts.justice.bg/Search/Details?actId="))
        self.assertIn("Определение", r["title"])
        self.assertEqual(r["observed"], "12.03.2026")
        self.assertIn("Софийски градски съд", r["snippet"])

    def test_every_row_has_url_and_observed_key(self):
        for r in self.rows:
            self.assertTrue(r["url"].startswith("https://legalacts.justice.bg"))
            self.assertIn("observed", r)
            self.assertTrue(r["title"])
