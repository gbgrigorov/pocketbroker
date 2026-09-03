"""Integration guard: the canonical registry contract against the REAL raw data.

These lock the Phase 2.0 findings so a future data refresh can't silently
regress coverage or start dropping an MVP neighbourhood's history.
"""

import glob
import json
import os
import unittest

from etl.build_registry import (CITIES, COORDS, CURRENT, CURRENT_RENT_GLOB, HISTORY_GLOB,
                                load_jsonl)
from etl.neighbourhoods import NameResolver, build_canonical_registry

# Every priced slug (sale + rent) that has a coordinate. Grew from the original 62
# once the missing 80 neighbourhoods were geocoded.
EXPECTED_MVP_COUNT = 142

# Outlying Sofia-municipality settlements (с. villages, гр. towns) are NOT part of
# the 1995–2025 imot.bg *city* history series, so they legitimately have no
# historical rows. Their slugs carry these prefixes.
SETTLEMENT_PREFIXES = ("s-", "gr-")


class TestRegistryAgainstRealData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.current = list(load_jsonl(CURRENT))
        for path in glob.glob(CURRENT_RENT_GLOB):
            cls.current += list(load_jsonl(path))
        with open(COORDS, encoding="utf-8") as fh:
            cls.coords = json.load(fh)
        cls.registry = build_canonical_registry(cls.current, cls.coords)

    def test_registry_has_expected_mvp_count(self):
        self.assertEqual(len(self.registry), EXPECTED_MVP_COUNT)

    def test_every_entry_has_coordinates(self):
        for slug, entry in self.registry.items():
            self.assertIsNotNone(entry["lat"], slug)
            self.assertIsNotNone(entry["lon"], slug)

    def test_every_city_neighbourhood_has_historical_rows(self):
        name_to_slug = {e["name"]: s for s, e in self.registry.items()}
        resolver = NameResolver(name_to_slug)
        seen = set()
        for path in glob.glob(HISTORY_GLOB):
            for rec in load_jsonl(path):
                slug = resolver.resolve(rec.get("neighborhood"))
                if slug is not None:
                    seen.add(slug)
        # Outlying settlements are exempt — they aren't in the city history series.
        city = {s for s in self.registry if not s.startswith(SETTLEMENT_PREFIXES)}
        missing = city - seen
        self.assertEqual(missing, set(),
                         f"city neighbourhoods with no historical rows: {missing}")


class TestAdditionalCitiesRegistry(unittest.TestCase):
    """The same registry contract for Varna / Burgas / Plovdiv, against real raw data.

    Skips a city whose raw data isn't present yet so the suite stays green on a
    fresh checkout; once a city is crawled + geocoded these assertions lock it in.
    """

    def _registry_for(self, cfg):
        current = [r for p in glob.glob(cfg["current_glob"]) for r in load_jsonl(p)]
        for p in glob.glob(cfg["current_rent_glob"]):
            current += list(load_jsonl(p))
        with open(cfg["coords"], encoding="utf-8") as fh:
            coords = json.load(fh)
        return build_canonical_registry(current, coords)

    def test_each_city_registry_nonempty_and_has_coords(self):
        for slug, cfg in CITIES.items():
            if not os.path.exists(cfg["coords"]) or not glob.glob(cfg["current_glob"]):
                self.skipTest(f"{slug} raw data not present")
            registry = self._registry_for(cfg)
            self.assertGreater(len(registry), 0, slug)
            for s, entry in registry.items():
                self.assertIsNotNone(entry["lat"], f"{slug}/{s}")
                self.assertIsNotNone(entry["lon"], f"{slug}/{s}")

    def test_each_city_has_historical_coverage(self):
        for slug, cfg in CITIES.items():
            if not os.path.exists(cfg["coords"]) or not glob.glob(cfg["current_glob"]):
                self.skipTest(f"{slug} raw data not present")
            registry = self._registry_for(cfg)
            resolver = NameResolver({e["name"]: s for s, e in registry.items()})
            seen = set()
            for p in glob.glob(cfg["history_glob"]):
                for rec in load_jsonl(p):
                    resolved = resolver.resolve(rec.get("neighborhood"))
                    if resolved is not None:
                        seen.add(resolved)
            # At least some mapped neighbourhoods appear in the history series.
            self.assertTrue(seen, f"{slug}: no historical rows resolved to the registry")


if __name__ == "__main__":
    unittest.main()
