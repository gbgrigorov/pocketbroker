"""Unit tests for the novitesgradi.bg new-build parsers (system python3 + bs4).

    python3 -m unittest crawlers.scraper_kit.tests.test_novitesgradi

The listing fixture is a trimmed copy of the real ``/novo-stroitelstvo`` index
(first few ``.rh_prop_card`` cards). The detail parser is additionally checked
against the full saved detail page under ``data/fixtures/`` when present.
"""

import unittest
from pathlib import Path

from crawlers.scraper_kit.sites.novitesgradi import (parse_detail, parse_listing,
                                                     transliterate, _slug)

FIX = Path(__file__).resolve().parent / "fixtures"
REPO = Path(__file__).resolve().parents[3]


class TestTransliteration(unittest.TestCase):
    def test_known_neighbourhoods(self):
        self.assertEqual(_slug("Кръстова вада"), "krastova-vada")
        self.assertEqual(_slug("Младост"), "mladost")
        self.assertEqual(_slug("Изгрев"), "izgrev")


class TestListingParser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recs = parse_listing((FIX / "novitesgradi_listing.html").read_text(encoding="utf-8"))

    def test_parses_cards(self):
        self.assertGreaterEqual(len(self.recs), 1)

    def test_card_fields(self):
        by_name = {r["project_name"]: r for r in self.recs}
        self.assertIn("Сграда ЕСТИР", by_name)
        estir = by_name["Сграда ЕСТИР"]
        self.assertEqual(estir["floors"], 9)
        self.assertEqual(estir["area_min_sqm"], 6800.0)
        self.assertIn("/сграда/", __import__("urllib.parse", fromlist=["unquote"]).unquote(estir["url"]))
        self.assertTrue(estir["price_on_request"])


class TestDetailParserRealPage(unittest.TestCase):
    def test_real_detail_if_present(self):
        real = REPO / "data" / "fixtures" / "new_buildings" / "novitesgradi" / "detail_sample.html"
        if not real.exists():
            self.skipTest("real detail fixture not present")
        rec = parse_detail(real.read_text(encoding="utf-8", errors="replace"))
        # Сграда ЕСТИР detail page: АРТЕКС ИНЖЕНЕРИНГ in Младост, Акт 16.
        self.assertEqual(rec["akt_stage"], "Акт 16")
        self.assertIsNotNone(rec["developer_name"])
        self.assertIsNotNone(rec["neighborhood"])
        self.assertEqual(rec["neighborhood_slug"], _slug(rec["neighborhood"]))


if __name__ == "__main__":
    unittest.main()
