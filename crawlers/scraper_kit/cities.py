"""City registry — multi-city by design.

Adding a city = add one entry here. New-building site scrapers read
``City.site_params[<site>]`` to build their per-city URLs; no framework or
normalizer code changes are needed to cover a new city.

The ``builders`` domain is national (КСБ/BRRA cover all of Bulgaria), so it is
scoped by country code (``bg``) rather than by a city in this registry.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class City:
    slug: str          # canonical ASCII slug, matches the `city` DB table
    name: str          # Cyrillic display name
    country: str       # ISO-ish country code, e.g. "bg"
    site_params: dict  # {site_key: {param: value}} used to build per-site URLs


CITIES = {
    "sofia": City(
        slug="sofia",
        name="София",
        country="bg",
        site_params={
            "novitesgradi": {"city_path": "софия"},
            "bulgarianproperties": {"city_path": "sofia"},
            "luximmo": {"region_path": "oblast-sofiya", "city_path": "sofiya"},
        },
    ),
    # Extend coverage by adding e.g. "plovdiv", "varna", "burgas" here with the
    # equivalent per-site path tokens — nothing else in the pipeline changes.
}


def get_city(slug: str) -> City:
    try:
        return CITIES[slug]
    except KeyError:
        known = ", ".join(sorted(CITIES))
        raise SystemExit(f"Unknown city '{slug}'. Known cities: {known}")
