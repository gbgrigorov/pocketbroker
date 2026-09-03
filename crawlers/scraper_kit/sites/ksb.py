"""КСБ / ЦПРС — Central Professional Register of Builders (register.ksb.bg).

The authoritative, free list of licensed construction companies in Bulgaria.
This is the seed of the builder universe (domain = ``builders``).

Mechanics (reverse-engineered 2026-05):
  POST https://register.ksb.bg/spravki.php
    findEIK=<eik> | findNAME=<prefix> | filter1=Търси вписани в регистъра
  -> one flat UTF-8 HTML table, NO pagination, columns:
       ЕИК | Строител (name) | Протокол No/Дата
  The name search is a PREFIX match (LIKE 'name%') and requires >= 3 chars.

Because there is no "list all", enumeration walks a seed list of name prefixes
and de-dupes by ЕИК. Two modes:

  default                : broad pull over SEED_PREFIXES (common builder roots)
  --names-file <path>    : targeted — resolve specific developer names (e.g. the
                           ones scraped from novitesgradi) to ЕИК + licence

    python3 -m crawlers.scraper_kit.run --domain builders --site ksb
    python3 -m crawlers.scraper_kit.sites.ksb --names-file data/dev_names.txt
"""

from __future__ import annotations

import time
from typing import Iterator, List, Optional

from crawlers.scraper_kit.base import BaseScraper

SPRAVKI_URL = "https://register.ksb.bg/spravki.php"
FILTER_REGISTERED = "Търси вписани в регистъра"

# Broad-coverage seed: high-frequency starting roots of BG construction-company
# names. De-duplication by ЕИК makes overlap harmless; extend freely.
SEED_PREFIXES: List[str] = [
    "стро", "строй", "строи", "билд", "инж", "инв", "арх", "арт", "гра", "гру",
    "дом", "еко", "ева", "евро", "зав", "зид", "имо", "кон", "кап", "люк",
    "май", "мон", "монолит", "над", "нов", "пан", "пла", "про", "ремонт", "рено",
    "сити", "тех", "уют", "фор", "хол", "цен", "build", "city", "grup", "invest",
]


class KsbScraper(BaseScraper):
    site = "ksb"
    domain = "builders"
    rate_limit_s = 1.0

    def __init__(self, scope: str = "bg", prefixes: Optional[List[str]] = None,
                 names: Optional[List[str]] = None):
        super().__init__(scope)
        self.prefixes = prefixes if prefixes is not None else SEED_PREFIXES
        self.names = names  # targeted mode: resolve these exact developer names

    def _search(self, *, eik: str = "", name: str = "") -> List[dict]:
        from bs4 import BeautifulSoup

        wait = self.rate_limit_s - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        # BaseScraper.get is GET-only; the КСБ search is a POST, so use the client directly.
        r = self._client.post(
            SPRAVKI_URL,
            data={"findEIK": eik, "findNAME": name, "filter1": FILTER_REGISTERED},
        )
        self._last_request = time.monotonic()
        self.stats.pages_fetched += 1
        self.stats.bytes_downloaded += len(r.content)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        rows: List[dict] = []
        tables = soup.find_all("table")
        if not tables:
            return rows
        for tr in tables[-1].find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all("td")]
            if len(cells) >= 3 and cells[0].isdigit() and len(cells[0]) in (9, 10, 13):
                rows.append({
                    "eik": cells[0],
                    "name": cells[1],
                    "ksb_protocol": cells[2],
                    "ksb_active": True,
                })
        return rows

    def scrape(self) -> Iterator[dict]:
        seen: set[str] = set()
        queries = (
            [("name", n) for n in self.names] if self.names
            else [("name", p) for p in self.prefixes]
        )
        for _, q in queries:
            try:
                results = self._search(name=q)
            except Exception as exc:  # noqa: BLE001
                self.stats.errors += 1
                self._log(f"query {q!r} failed: {exc}")
                continue
            new = 0
            for rec in results:
                if rec["eik"] in seen:
                    continue
                seen.add(rec["eik"])
                new += 1
                yield rec
            self._log(f"prefix {q!r}: {len(results)} rows, {new} new (total {len(seen)})")


SCRAPER = KsbScraper


def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="КСБ register scraper")
    parser.add_argument("--names-file", help="newline-separated developer names to resolve")
    parser.add_argument("--prefix", help="single ad-hoc name prefix to search")
    args = parser.parse_args()

    names = None
    prefixes = None
    if args.names_file:
        with open(args.names_file, encoding="utf-8") as fh:
            names = [ln.strip() for ln in fh if ln.strip()]
    if args.prefix:
        prefixes = [args.prefix]
    KsbScraper("bg", prefixes=prefixes, names=names).run()


if __name__ == "__main__":
    _cli()
