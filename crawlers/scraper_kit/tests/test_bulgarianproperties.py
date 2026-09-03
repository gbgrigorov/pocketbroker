"""Tests for the BULGARIANPROPERTIES scraper.

The scraper is currently a non-functional stub (the prior draft was built on a
fictional page structure derived from 404 pages — see
docs/NEW_BUILDINGS_CRAWL_REPORT_2026-06-01.md). These tests are skipped until the
real site structure is reverse-engineered and parsers are implemented.

    python3 -m unittest crawlers.scraper_kit.tests.test_bulgarianproperties
"""

import unittest


@unittest.skip("bulgarianproperties scraper is a stub pending real structure")
class TestBulgarianPropertiesPending(unittest.TestCase):
    def test_placeholder(self):
        pass


if __name__ == "__main__":
    unittest.main()
