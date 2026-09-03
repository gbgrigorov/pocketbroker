"""BaseScraper — fetch + parse with per-run telemetry.

Every site scraper subclasses :class:`BaseScraper` and implements :meth:`scrape`
as a generator of ``dict`` records. The base class provides:

- a rate-limited, retrying httpx client with sane headers,
- optional fixed encoding (e.g. ``windows-1251`` for imot.bg),
- byte/page/record counters written as a sidecar ``<output>.stats.json`` manifest
  next to the raw JSONL (the "how much data did we process" flex counter).

Output layout (per site, per scope, per run)::

    data/raw/<domain>/<scope>/<site>_<YYYY-MM-DD>_<run-id>.jsonl
    data/raw/<domain>/<scope>/<site>_<YYYY-MM-DD>_<run-id>.stats.json

``scope`` is the city slug for the ``new_buildings`` domain and the country code
(e.g. ``bg``) for the national ``builders`` domain. ``run-id`` is a random
8-hex-char token so two runs on the same day never share a file — a later
run truncating an earlier one's records was a real, recurring data-loss bug.
"""

from __future__ import annotations

import datetime as _dt
import json
import secrets
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator, Optional

import httpx

# repo_root/data  (this file is repo_root/crawlers/scraper_kit/base.py)
DATA_ROOT = Path(__file__).resolve().parents[2] / "data"

# BGN/EUR fixed peg (matches crawlers/imot_prices.py)
BGN_PER_EUR = 1.95583

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; BG-RE-Research/1.0; +https://github.com/bg-realestate)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "bg,en;q=0.8",
}


def _utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


@dataclass
class RunStats:
    """Telemetry for a single scraper run — persisted to ``crawl_run`` via ETL."""

    domain: str
    site: str
    scope: str
    pages_fetched: int = 0
    bytes_downloaded: int = 0
    records_parsed: int = 0
    records_emitted: int = 0
    errors: int = 0
    duration_s: float = 0.0
    started_at: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


class BaseScraper:
    """Subclass per website; set the class attributes and implement :meth:`scrape`."""

    site: str = "base"          # short site key, e.g. "ksb" / "novitesgradi"
    domain: str = "builders"    # "builders" | "new_buildings"
    rate_limit_s: float = 1.0   # polite minimum delay between requests
    encoding: Optional[str] = None  # force response encoding, e.g. "windows-1251"
    file_tag: str = ""          # optional output-filename discriminator (e.g. "persons")

    def __init__(self, scope: str):
        self.scope = scope
        self.stats = RunStats(
            domain=self.domain, site=self.site, scope=scope, started_at=_utcnow()
        )
        self._last_request = 0.0
        self._client = httpx.Client(headers=HEADERS, timeout=30.0, follow_redirects=True)

    # --- fetching -----------------------------------------------------------

    def get(self, url: str, **kwargs) -> httpx.Response:
        """Rate-limited GET with up to 3 retries; updates byte/page counters."""
        wait = self.rate_limit_s - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        last_exc: Optional[Exception] = None
        for attempt in range(3):
            try:
                resp = self._client.get(url, **kwargs)
                self._last_request = time.monotonic()
                resp.raise_for_status()
                self.stats.pages_fetched += 1
                self.stats.bytes_downloaded += len(resp.content)
                if self.encoding:
                    resp.encoding = self.encoding
                return resp
            except Exception as exc:  # noqa: BLE001 - record and retry
                last_exc = exc
                self.stats.errors += 1
                if attempt < 2:
                    time.sleep(2 ** attempt)
        self._log(f"GET failed after retries: {url}: {last_exc}")
        raise last_exc  # type: ignore[misc]

    def soup(self, url: str, **kwargs):
        """Fetch ``url`` and return a BeautifulSoup tree (lazy import)."""
        from bs4 import BeautifulSoup

        resp = self.get(url, **kwargs)
        return BeautifulSoup(resp.text, "html.parser")

    # --- override -----------------------------------------------------------

    def scrape(self) -> Iterator[dict]:
        """Yield one dict per entity. Subclasses must implement."""
        raise NotImplementedError

    # --- orchestration ------------------------------------------------------

    def run(self) -> Path:
        out_dir = DATA_ROOT / "raw" / self.domain / self.scope
        out_dir.mkdir(parents=True, exist_ok=True)
        today = _dt.date.today().isoformat()
        stem = f"{self.site}_{self.file_tag}" if self.file_tag else self.site
        out_path = out_dir / f"{stem}_{today}_{secrets.token_hex(4)}.jsonl"

        t0 = time.monotonic()
        with out_path.open("w", encoding="utf-8") as fh:
            for rec in self.scrape():
                self.stats.records_parsed += 1
                rec.setdefault("source_site", self.site)
                rec.setdefault("scope", self.scope)
                rec.setdefault("scraped_at", _utcnow())
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                self.stats.records_emitted += 1
        self.stats.duration_s = round(time.monotonic() - t0, 2)

        stats_path = out_path.with_name(out_path.stem + ".stats.json")
        stats_path.write_text(
            json.dumps(self.stats.as_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._log(
            f"{self.site}/{self.scope}: {self.stats.records_emitted} records, "
            f"{self.stats.pages_fetched} pages, "
            f"{self.stats.bytes_downloaded / 1e6:.2f} MB, "
            f"{self.stats.duration_s}s -> {out_path}"
        )
        return out_path

    def _log(self, msg: str) -> None:
        print(f"[{self.site}] {msg}", file=sys.stderr)
