"""Papagal (papagal.bg) — per-ЕИК ownership / management edges.

Papagal aggregates the Commercial Register into one HTML page per company at
``/eik/{eik}/{hash}``. We resolve a company's page from its ЕИК, then read the
structured ``<dl>`` fact rows to emit a company node plus its direct edges:

- **Собственост** → "Действителен собственик" (UBO) → an *ownership* edge,
  person → this company.
- **Представляващи** / **Ръководни органи** → *management* edges, person → company.
- linked **companies** (``/eik/…``) inside an ownership block → company → company.

Persons have no ЕИК; Papagal links them as ``/p/{hash}`` — that hash is a stable
``person_key`` (the dedup key the plan calls for). Output domain = ``ownership``;
one raw record per company::

    {eik, name, legal_form, status, address, capital_eur,
     related: [{kind, name, eik?|person_key?, relation, role, direction, is_current}]}

``direction`` is ``"in"`` (related → this company, e.g. owner/manager) or
``"out"`` (this company → related, e.g. subsidiary); the ETL turns that into a
directed ``entity_edge``. Provenance is recorded as ``source = "papagal"``.

    python3 -m crawlers.scraper_kit.sites.papagal --eik 831641791
    python3 -m crawlers.scraper_kit.sites.papagal --eiks-file data/seed_eiks.txt
"""

from __future__ import annotations

import re
import time
from typing import Iterator, List, Optional

from crawlers.scraper_kit.base import BaseScraper

BASE = "https://papagal.bg"

# dt-label -> (relation, direction) for the relationship fact rows.
RELATION_ROWS = {
    "Собственост": ("ownership", "in"),       # Действителен собственик (UBO)
    "Представляващи": ("management", "in"),    # Представител
    "Ръководни органи": ("management", "in"),  # Съвет на директорите / Управител
}


def _clean(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    return re.sub(r"\s+", " ", text).strip() or None


# Status phrases (lowercased substring match) that indicate a distressed company.
_DISTRESS_STATUS = ("несъстоятел", "ликвидаци", "заличен")


def insolvency_from_status(status: Optional[str]) -> bool:
    """True if a Papagal ``Статус`` string indicates insolvency/liquidation/erasure.

    Conservative substring match on the Bulgarian status text; "Активен" → False.
    """
    if not status:
        return False
    low = status.lower()
    return any(token in low for token in _DISTRESS_STATUS)


def _person_key(href: str) -> str:
    """Stable person id from a ``/p/{hash}/{nonce}`` link (drop the page nonce)."""
    tail = href.split("/p/", 1)[1]
    return tail.split("/", 1)[0]


def _parse_reg_year(text: Optional[str]) -> Optional[int]:
    """Year from Papagal's "Дата на регистрация" (e.g. "2002 година" or a full date)."""
    if not text:
        return None
    m = re.search(r"((?:19|20)\d{2})", text)
    return int(m.group(1)) if m else None


BGN_PER_EUR = 1.95583  # fixed peg (matches the ETL's EUR->BGN conversion)


def _parse_capital_eur(text: Optional[str]) -> Optional[float]:
    """Registered capital in EUR from Papagal's "Капитал размер".

    Newer companies show euros ("2 556 €"); older / struck-off ones show лева
    ("5 000 лева внесен"). Read either — лева is converted at the fixed peg so the
    ETL's EUR->BGN step restores the nominal BGN capital without extra rounding.
    """
    if not text:
        return None
    m = re.search(r"([\d\s .,]+?)\s*€", text)
    if m:
        digits = re.sub(r"[^\d]", "", m.group(1))
        return float(digits) if digits else None
    m = re.search(r"([\d\s .,]+?)\s*(?:лева|лв\.?|BGN)", text)
    if m:
        digits = re.sub(r"[^\d]", "", m.group(1))
        return float(digits) / BGN_PER_EUR if digits else None
    return None


def parse_company(html: str, eik: str) -> dict:
    """Parse a Papagal company page into a node + its direct edge records."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    facts = {}
    for dl in soup.find_all("dl"):
        dts, dds = dl.find_all("dt"), dl.find_all("dd")
        for dt, dd in zip(dts, dds):
            facts.setdefault(_clean(dt.get_text(" ", strip=True)), dd)

    def text_of(key):
        dd = facts.get(key)
        return _clean(dd.get_text(" ", strip=True)) if dd else None

    related: List[dict] = []
    for key, (relation, direction) in RELATION_ROWS.items():
        dd = facts.get(key)
        if dd is None:
            continue
        # Role = the label before the first colon, e.g. "Действителен собственик".
        role = _clean((dd.get_text(" ", strip=True).split(":", 1)[0]))
        for a in dd.find_all("a", href=True):
            href = a["href"]
            name = _clean(a.get_text(strip=True))
            if not name:
                continue
            if href.startswith("/p/"):
                related.append({
                    "kind": "person", "name": name, "person_key": _person_key(href),
                    "relation": relation, "role": role,
                    "direction": direction, "is_current": True,
                })
            elif "/eik/" in href:
                rel_eik = href.split("/eik/", 1)[1].split("/", 1)[0]
                if rel_eik == eik:
                    continue  # self-link
                related.append({
                    "kind": "company", "name": name, "eik": rel_eik,
                    "relation": relation, "role": role,
                    "direction": direction, "is_current": True,
                })

    return {
        "eik": eik,
        "name": text_of("Наименование"),
        "legal_form": text_of("Правна форма"),
        "status": text_of("Статус"),
        "address": text_of("Седалище адрес"),
        "capital_eur": _parse_capital_eur(text_of("Капитал размер")),
        "founded_year": _parse_reg_year(text_of("Дата на регистрация")),
        "related": related,
    }


# Ordered role phrases (longest/most-specific first) for person-page rows.
_ROLE_PHRASES = [
    "Едноличен собственик на капитала", "Действителен собственик",
    "Член на съвета на директорите", "Член на управителния съвет",
    "Представляващ", "Управител", "Прокурист", "Съдружник", "Акционер", "Собственик",
]
_OWNERSHIP_HINTS = ("собственик", "Съдружник", "Акционер", "дял", "капитал")
_MANAGEMENT_HINTS = ("Управител", "Представл", "директор", "Прокурист", "управителния")


def _relation_and_role(text: str) -> tuple:
    role = next((p for p in _ROLE_PHRASES if p in text), None)
    if any(h in text for h in _OWNERSHIP_HINTS):
        relation = "ownership"
    elif any(h in text for h in _MANAGEMENT_HINTS):
        relation = "management"
    else:
        relation = "ownership"
    return relation, role


def parse_person(html: str, person_key: str) -> dict:
    """Parse a Papagal person page into that person's company participations.

    Rows live in ``div.mb-3.ps-3``; ``text-success`` = current, ``text-danger`` =
    historical — but note that *several* historical rows are also marked
    text-success, so ``share_pct`` is NOT read here (see the comment below).
    The chronology table is ignored. Returns a ``person_participations`` record::

        {kind, person_key, name, companies: [{kind, eik, name, relation, role,
                                              share_pct, is_current}]}
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    name = None
    for h in soup.find_all(["h1", "h2"]):
        t = h.get_text(" ", strip=True)
        if "свързани" in t:
            name = _clean(re.split(r"\s*[-–]\s*свързани", t)[0])
            break
    if name is None:
        heading = soup.find(["h1", "h2"])
        name = _clean(heading.get_text(" ", strip=True)) if heading else None

    companies: dict = {}
    for div in soup.find_all("div", class_="ps-3"):
        classes = div.get("class") or []
        if "mb-3" not in classes:
            continue
        a = div.find("a", href=lambda h: h and "/eik/" in h)
        if not a:
            continue
        eik = a["href"].split("/eik/", 1)[1].split("/", 1)[0]
        text = div.get_text(" ", strip=True)
        is_current = "text-success" in classes
        relation, role = _relation_and_role(text)

        # share_pct is deliberately NOT taken from this page.
        #
        # Papagal lists a person's whole ownership *history* as sibling rows and
        # marks several of them text-success, not just the latest. Георги Георгиев in
        # Смарт Хаус Къмпани (203879071) renders as 50%, 34% AND 26% all "current";
        # the true figure is 26% (confirmed against the Търговски регистър, where
        # his share is 1300 of 5000 лв). Taking the first match recorded 50% —
        # the oldest value — and that mistake is already in ~1750 edges.
        #
        # There is no reliable ordering to pick from, so shares come from the
        # register instead: registryagency.py field 19 gives the current amount
        # in лв. See docs/OFFICIAL_DATA_SOURCES.md.
        share_pct = None

        item = {
            "kind": "company", "eik": eik, "name": _clean(a.get_text(strip=True)),
            "relation": relation, "role": role,
            "share_pct": share_pct, "is_current": is_current,
        }
        key = (eik, relation)
        # Prefer the current row if the same (company, relation) appears twice.
        if key not in companies or (is_current and not companies[key]["is_current"]):
            companies[key] = item

    return {
        "kind": "person_participations",
        "person_key": person_key,
        "name": name,
        "companies": list(companies.values()),
    }


class PapagalScraper(BaseScraper):
    site = "papagal"
    domain = "ownership"
    rate_limit_s = 1.5  # be polite to a third-party aggregator

    def __init__(self, scope: str = "bg", eiks: Optional[List[str]] = None,
                 persons: Optional[List[dict]] = None):
        super().__init__(scope)
        self.eiks = eiks or []
        self.persons = persons or []  # [{"name", "person_key"}] for depth-2 expansion
        if self.persons:
            self.file_tag = "persons"  # keep depth-2 output distinct from company runs

    def _resolve_path(self, eik: str) -> Optional[str]:
        """ЕИК -> ``/eik/{eik}/{hash}`` company-page path via the search results."""
        soup = self.soup(f"{BASE}/search_results/{eik}?type=company")
        for a in soup.find_all("a", href=True):
            if a["href"].startswith(f"/eik/{eik}/"):
                return a["href"]
        return None

    def _resolve_person_path(self, name: str, person_key: str) -> Optional[str]:
        """Find ``/p/{person_key}/{nonce}`` by name-searching, matching the exact key.

        Persons have no stable bare URL; the page nonce is only handed out via
        search. Matching on ``person_key`` keeps the right person even for
        common names.
        """
        wait = self.rate_limit_s - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        r = self._client.post(f"{BASE}/s", data={"query": name})
        self._last_request = time.monotonic()
        self.stats.pages_fetched += 1
        self.stats.bytes_downloaded += len(r.content)
        r.raise_for_status()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("/p/") and href.split("/p/", 1)[1].split("/", 1)[0] == person_key:
                return href
        return None

    def scrape(self) -> Iterator[dict]:
        if self.persons:
            yield from self._scrape_persons()
        else:
            yield from self._scrape_companies()

    def _scrape_companies(self) -> Iterator[dict]:
        for eik in self.eiks:
            try:
                path = self._resolve_path(eik)
                if not path:
                    self._log(f"{eik}: no company page found")
                    continue
                resp = self.get(f"{BASE}{path}")
                rec = parse_company(resp.text, eik)
                rec["source"] = self.site
                yield rec
            except Exception as exc:  # noqa: BLE001 - one ЕИК failing must not abort the rest
                self.stats.errors += 1
                self._log(f"{eik} failed: {exc}")

    def _scrape_persons(self) -> Iterator[dict]:
        for p in self.persons:
            name, key = p.get("name"), p.get("person_key")
            if not name or not key:
                continue
            try:
                path = self._resolve_person_path(name, key)
                if not path:
                    self._log(f"{key} ({name}): no person page found")
                    continue
                resp = self.get(f"{BASE}{path}")
                rec = parse_person(resp.text, key)
                rec["source"] = self.site
                yield rec
            except Exception as exc:  # noqa: BLE001
                self.stats.errors += 1
                self._log(f"{key} ({name}) failed: {exc}")


SCRAPER = PapagalScraper


def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Papagal ownership scraper (companies or persons)")
    parser.add_argument("--eik", help="single ЕИК to scrape (company mode)")
    parser.add_argument("--eiks-file", help="newline-separated ЕИК list (company mode)")
    parser.add_argument("--persons-file",
                        help="depth-2: TSV 'person_key\\tname' per line (person mode)")
    args = parser.parse_args()

    if args.persons_file:
        persons: List[dict] = []
        with open(args.persons_file, encoding="utf-8") as fh:
            for ln in fh:
                parts = ln.rstrip("\n").split("\t")
                if len(parts) >= 2 and parts[0].strip():
                    persons.append({"person_key": parts[0].strip(), "name": parts[1].strip()})
        PapagalScraper("bg", persons=persons).run()
        return

    eiks: List[str] = []
    if args.eik:
        eiks = [args.eik]
    elif args.eiks_file:
        with open(args.eiks_file, encoding="utf-8") as fh:
            eiks = [ln.strip() for ln in fh if ln.strip()]
    else:
        parser.error("provide --eik, --eiks-file, or --persons-file")
    PapagalScraper("bg", eiks=eiks).run()


if __name__ == "__main__":
    _cli()
