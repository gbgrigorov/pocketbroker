"""BULGARIANPROPERTIES (bulgarianproperties.com) — NON-FUNCTIONAL STUB.

⚠️  This scraper is intentionally NOT implemented. An earlier draft was built on a
fictional page structure (the ``/realestates/newdev`` listing URL **404s**, and a
``RNT-#####`` detail pattern / "Act 16 / 2025" labels were inferred from 404
pages read while the Read cache was briefly serving stale content). That draft was
removed to avoid shipping code that looks right but parses nothing.

Reliable findings about the real site (2026-06-01), for whoever rebuilds this:

  * The "New Developments" listing URL is NOT ``/realestates/newdev`` (404).
  * Real detail pages are old-style ``AD#####BG`` ``.html`` pages, e.g.
    ``/Apartments_(various_types)_in_Bulgaria/AD82111BG_Apartments_(various_types)_for_sale_in_Sofia.html``
  * Other entry points seen on the homepage: ``/new-offers.html``,
    ``/Sofia_property/index.html``.

TODO (interactive session): locate the real Sofia new-construction category,
reverse-engineer one ``AD#####BG`` detail page, then implement ``parse_listing`` /
``parse_detail`` + a unittest against a real saved fixture, mirroring
``sites/novitesgradi.py`` once that exists. See
``docs/NEW_BUILDINGS_CRAWL_REPORT_2026-06-01.md``.
"""

from __future__ import annotations

from typing import Iterator

from crawlers.scraper_kit.base import BaseScraper


class BulgarianPropertiesScraper(BaseScraper):
    site = "bulgarianproperties"
    domain = "new_buildings"

    def scrape(self) -> Iterator[dict]:
        raise NotImplementedError(
            "bulgarianproperties scraper is a stub — the real listing URL/detail "
            "structure still needs reverse-engineering (the previous draft was "
            "built on 404 pages). See docs/NEW_BUILDINGS_CRAWL_REPORT_2026-06-01.md"
        )
        yield  # pragma: no cover  (makes this a generator)


SCRAPER = BulgarianPropertiesScraper
