"""Parser tests for the Papagal company page (run under system python3).

    python3 -m unittest crawlers.scraper_kit.tests.test_papagal

Uses a saved real fixture (ЕИК 831641791) so no network is touched. bs4 is a
crawler dependency; pytest is not installed for the scraper interpreter, so these
use stdlib :mod:`unittest`.
"""

import unittest
from pathlib import Path

from crawlers.scraper_kit.sites.papagal import (BGN_PER_EUR, _parse_capital_eur,
                                                insolvency_from_status, parse_company,
                                                parse_person)

FIXTURE = Path(__file__).parent / "fixtures" / "papagal_831641791.html"
PERSON_FIXTURE = Path(__file__).parent / "fixtures" / "papagal_person_sample.html"
PERSON_KEY = "5781873d0b874daa832ff9312ad38807aa9f17499a1f54124ad1ca0c7337aed4-1"


@unittest.skipUnless(FIXTURE.exists(), "saved papagal fixture not present (kept out of git)")
class ParseCompanyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rec = parse_company(FIXTURE.read_text(encoding="utf-8"), "831641791")

    def test_identity_fields(self):
        rec = self.rec
        self.assertEqual(rec["eik"], "831641791")
        self.assertEqual(rec["name"], "ИНФОРМАЦИОННО ОБСЛУЖВАНЕ")
        self.assertEqual(rec["status"], "Активен")
        self.assertIn("Акционерно", rec["legal_form"])
        self.assertIn("София", rec["address"])
        self.assertEqual(rec["capital_eur"], 1172232.0)

    def test_capital_leva_round_trips_to_bgn(self):
        # Older / struck-off companies show capital in лева, not euros. Parsing to
        # EUR then applying the ETL's peg must restore the nominal BGN amount.
        for leva, nominal_bgn in [("5 000 лева (5 000 лева внесен)", 5000),
                                  ("2 лева (2 лева внесен)", 2),
                                  ("1 592 110 лева внесен", 1592110)]:
            eur = _parse_capital_eur(leva)
            self.assertIsNotNone(eur)
            self.assertEqual(round(eur * BGN_PER_EUR, 2), float(nominal_bgn))

    def test_capital_euro_still_parsed(self):
        self.assertEqual(_parse_capital_eur("2 556 €"), 2556.0)

    def test_capital_missing_is_none(self):
        self.assertIsNone(_parse_capital_eur(None))
        self.assertIsNone(_parse_capital_eur("—"))

    def test_beneficial_owner_edge(self):
        owners = [r for r in self.rec["related"]
                  if r["relation"] == "ownership" and r["kind"] == "person"]
        self.assertTrue(owners, "expected a beneficial-owner edge")
        ivaylo = next(r for r in owners if r["name"] == "Петър Николов Петров")
        self.assertEqual(ivaylo["direction"], "in")  # person -> company
        self.assertIn("Действителен собственик", ivaylo["role"])
        self.assertTrue(ivaylo["person_key"].startswith("2f61a0d1"))
        self.assertTrue(ivaylo["is_current"])

    def test_management_edges(self):
        mgrs = [r for r in self.rec["related"] if r["relation"] == "management"]
        names = {r["name"] for r in mgrs}
        self.assertIn("Николай Стоянов Николов", names)
        self.assertTrue(all(r["kind"] == "person" and r["direction"] == "in" for r in mgrs))

    def test_person_keys_are_clean(self):
        for r in self.rec["related"]:
            if r["kind"] == "person":
                self.assertFalse(r["person_key"].startswith("/p/"))
                self.assertNotIn(" ", r["person_key"])
                # the trailing per-page nonce segment must be stripped
                self.assertLess(r["person_key"].count("/"), 1)


@unittest.skipUnless(PERSON_FIXTURE.exists(), "saved papagal fixture not present (kept out of git)")
class ParsePersonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rec = parse_person(PERSON_FIXTURE.read_text(encoding="utf-8"), PERSON_KEY)

    def _company(self, eik):
        return next(c for c in self.rec["companies"] if c["eik"] == eik)

    def test_identity_and_count(self):
        self.assertEqual(self.rec["person_key"], PERSON_KEY)
        self.assertEqual(self.rec["name"], "СТОЯН ПЕТРОВ СТОЯНОВ")
        # 8 distinct companies (5 current + 3 historical), not the chronology noise.
        eiks = {c["eik"] for c in self.rec["companies"]}
        self.assertGreaterEqual(len(eiks), 8)

    def test_current_participation(self):
        self.assertTrue(self._company("101770916")["is_current"])   # ИНЕРТСТРОЙ 33
        # ПИЯНОТО has both current + share-history rows -> collapses to ONE current entry
        pianoto = [c for c in self.rec["companies"] if c["eik"] == "206545792"]
        self.assertEqual(len(pianoto), 1)
        self.assertTrue(pianoto[0]["is_current"])

    def test_historical_only_marks_not_current(self):
        # A red (text-danger) row with no current counterpart -> is_current False.
        html = (
            '<h1>ИВАН ПЕТРОВ - свързани фирми</h1>'
            '<div class="mb-3 ps-3 text-danger">'
            '  Съдружник <a href="/eik/123456789/ab12">СТАРА ФИРМА</a> ( 40% дял )'
            '</div>'
        )
        rec = parse_person(html, "ivan-key")
        c = rec["companies"][0]
        self.assertEqual(c["eik"], "123456789")
        self.assertFalse(c["is_current"])
        self.assertEqual(c["share_pct"], 40.0)

    def test_share_pct_and_relation(self):
        verde = self._company("101647536")  # ВЕРДЕ ТУРС — Съдружник 25%
        self.assertEqual(verde["share_pct"], 25.0)
        self.assertEqual(verde["relation"], "ownership")

    def test_all_companies_well_formed(self):
        for c in self.rec["companies"]:
            self.assertEqual(c["kind"], "company")
            self.assertTrue(c["eik"].isdigit())
            self.assertIn(c["relation"], ("ownership", "management"))


class InsolvencyFromStatusTest(unittest.TestCase):
    def test_active_is_false(self):
        self.assertFalse(insolvency_from_status("Активен"))

    def test_none_is_false(self):
        self.assertFalse(insolvency_from_status(None))

    def test_insolvency_true(self):
        self.assertTrue(insolvency_from_status("В несъстоятелност"))

    def test_liquidation_true(self):
        self.assertTrue(insolvency_from_status("В ликвидация"))

    def test_deleted_true(self):
        self.assertTrue(insolvency_from_status("Заличен"))


if __name__ == "__main__":
    unittest.main()
