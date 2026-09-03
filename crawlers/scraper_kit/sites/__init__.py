"""Per-site scrapers. One module per website; each exposes ``SCRAPER`` (a
:class:`~crawlers.scraper_kit.base.BaseScraper` subclass).

Discovery is by filename: ``--site all`` loads every module in this package
whose ``SCRAPER.domain`` matches the requested domain. To add a website, drop a
new ``<site>.py`` here defining ``SCRAPER`` — no central registry to edit.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Dict, List, Type

from crawlers.scraper_kit.base import BaseScraper


def _iter_module_names() -> List[str]:
    return [m.name for m in pkgutil.iter_modules(__path__) if not m.name.startswith("_")]


def load_scraper(site: str) -> Type[BaseScraper]:
    """Import ``sites.<site>`` and return its ``SCRAPER`` class."""
    mod = importlib.import_module(f"{__name__}.{site}")
    scraper = getattr(mod, "SCRAPER", None)
    if scraper is None or not issubclass(scraper, BaseScraper):
        raise SystemExit(f"Site module '{site}' must define SCRAPER (a BaseScraper subclass).")
    return scraper


def discover(domain: str | None = None) -> Dict[str, Type[BaseScraper]]:
    """Return ``{site_key: SCRAPER}`` for all site modules, optionally filtered by domain."""
    found: Dict[str, Type[BaseScraper]] = {}
    for name in _iter_module_names():
        try:
            scraper = load_scraper(name)
        except SystemExit:
            continue
        if domain is None or scraper.domain == domain:
            found[name] = scraper
    return found
