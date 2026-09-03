"""Pure-helper tests for official-tier signal shaping (system python3, stdlib unittest).

    python3 -m unittest crawlers.scraper_kit.tests.test_official
"""
import unittest
from datetime import date

from crawlers.signals.official import act_mentions_eik, parse_bg_date, to_registry_row


class EikConfirmTest(unittest.TestCase):
    def test_matches_eik_with_spaces_and_label(self):
        text = "по описа на дружеството с ЕИК 175 155 346, гр. София"
        self.assertTrue(act_mentions_eik(text, "175155346"))

    def test_matches_bare_eik(self):
        self.assertTrue(act_mentions_eik("...ЕИК175155346...", "175155346"))

    def test_rejects_when_absent(self):
        self.assertFalse(act_mentions_eik("Артекс Инженеринг АД, гр. София", "175155346"))

    def test_rejects_substring_of_longer_number(self):
        # 175155346 must not match inside 1751553460000
        self.assertFalse(act_mentions_eik("сметка 1751553460000", "175155346"))


class BgDateTest(unittest.TestCase):
    def test_iso(self):
        self.assertEqual(parse_bg_date("2019-07-25"), date(2019, 7, 25))

    def test_dotted(self):
        self.assertEqual(parse_bg_date("25.07.2019"), date(2019, 7, 25))

    def test_none(self):
        self.assertIsNone(parse_bg_date("неизвестно"))


class RowShapeTest(unittest.TestCase):
    def test_row(self):
        row = to_registry_row(eik="175155346", name="АРТЕКС ИНЖЕНЕРИНГ АД",
                              url="https://legalacts.justice.bg/Search/Details/123",
                              title="Решение № 5", snippet="…", observed="2019-07-25")
        self.assertEqual(row["matched_eik"], "175155346")
        self.assertEqual(row["matched_name"], "АРТЕКС ИНЖЕНЕРИНГ АД")
        self.assertEqual(row["source_site"], "legalacts")
        self.assertEqual(row["observed_date"], "2019-07-25")
        self.assertEqual(row["url"], "https://legalacts.justice.bg/Search/Details/123")
