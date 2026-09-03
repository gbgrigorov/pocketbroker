import unittest

from etl.neighbourhoods import NameResolver, build_canonical_registry


class TestNameResolver(unittest.TestCase):
    def setUp(self):
        # Canonical registry: title-case Bulgarian name -> slug (as in current snapshot)
        self.name_to_slug = {
            "Банишора": "banishora",
            "Белите брези": "belite-brezi",
            "Лозенец": "lozenets",
        }
        # Hand-curated aliases for historical strings that don't normalise to a canonical name
        self.aliases = {"БЕЛИ БРЕЗИ": "belite-brezi"}
        self.resolver = NameResolver(self.name_to_slug, self.aliases)

    def test_resolves_exact_current_name(self):
        self.assertEqual(self.resolver.resolve("Лозенец"), "lozenets")

    def test_resolves_all_caps_historical_name(self):
        self.assertEqual(self.resolver.resolve("БАНИШОРА"), "banishora")

    def test_strips_surrounding_whitespace(self):
        self.assertEqual(self.resolver.resolve("  Банишора "), "banishora")

    def test_resolves_divergent_string_via_alias(self):
        self.assertEqual(self.resolver.resolve("БЕЛИ БРЕЗИ"), "belite-brezi")

    def test_returns_none_for_unknown_name(self):
        self.assertIsNone(self.resolver.resolve("Несъществуващ"))

    def test_returns_none_for_none_input(self):
        self.assertIsNone(self.resolver.resolve(None))


class TestBuildCanonicalRegistry(unittest.TestCase):
    def setUp(self):
        self.current_records = [
            {"neighborhood": "Лозенец", "neighborhood_slug": "lozenets"},
            {"neighborhood": "Лозенец", "neighborhood_slug": "lozenets"},  # duplicate type row
            {"neighborhood": "Банишора", "neighborhood_slug": "banishora"},
            {"neighborhood": "Без координати", "neighborhood_slug": "no-coords"},
        ]
        self.coords = {
            "lozenets": {"name": "Лозенец", "lat": 42.66, "lon": 23.32, "source": "nominatim"},
            "banishora": {"name": "Банишора", "lat": 42.71, "lon": 23.31, "source": "osm_quarter"},
            "orphan": {"name": "Сирак", "lat": 42.7, "lon": 23.3, "source": "nominatim"},
        }

    def test_includes_only_slugs_present_in_both(self):
        registry = build_canonical_registry(self.current_records, self.coords)
        self.assertEqual(set(registry.keys()), {"lozenets", "banishora"})

    def test_entry_merges_name_and_coords(self):
        registry = build_canonical_registry(self.current_records, self.coords)
        self.assertEqual(
            registry["lozenets"],
            {"slug": "lozenets", "name": "Лозенец", "lat": 42.66, "lon": 23.32, "coord_source": "nominatim"},
        )

    def test_excludes_current_without_coords(self):
        registry = build_canonical_registry(self.current_records, self.coords)
        self.assertNotIn("no-coords", registry)

    def test_excludes_coords_without_price(self):
        registry = build_canonical_registry(self.current_records, self.coords)
        self.assertNotIn("orphan", registry)


if __name__ == "__main__":
    unittest.main()
