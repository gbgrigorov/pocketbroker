"""novitesgradi.bg — Sofia new-building *developments* (the primary new-build source).

novitesgradi.bg ("Нови сгради в София") is a Sofia-focused catalogue of new
construction. It is a WordPress + **RealHomes** site; the new-construction index
``/novo-stroitelstvo`` renders ``.rh_prop_card`` cards, one per **named
development** (e.g. "Сграда ЕСТИР", "ТАВИТА", "River Park"). Each card links to a
``/сграда/{slug}/`` detail page.

From the **listing card** we get (reliable, one request):
    name, detail url, floors (Етажи), area m² (Квадратура), building type, price
    ("цена при запитване" = price on request -> None).

From the **detail page** we enrich (best-effort, resilient to layout):
    neighbourhood (Квартал/Район), developer / инвеститор, completion stage
    (Акт 14/15/16) + year, construction materials.

Emits the field names the new-buildings normalizer reads (``project_name``,
``url``, ``neighborhood``, ``neighborhood_slug``, ``developer_name``,
``price_eur_sqm``, ``akt_stage``, ``completion_year``, ``floors``, ``materials``,
``area_min_sqm``, ``area_max_sqm``); ``source_site``/``scope``/``scraped_at`` are
added by :meth:`BaseScraper.run`.

    python3 -m crawlers.scraper_kit.sites.novitesgradi --city sofia
"""

from __future__ import annotations

import re
from typing import Iterator, List, Optional
from urllib.parse import urljoin, unquote

from crawlers.scraper_kit.base import BaseScraper

BASE = "https://novitesgradi.bg"
LISTING = "/novo-stroitelstvo"

# Bulgarian -> Latin transliteration (official streamlined system) for slug-matching
# against the existing neighbourhood slugs (e.g. "Кръстова вада" -> "krastova-vada").
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "zh", "з": "z",
    "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p",
    "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "sht", "ъ": "a", "ь": "y", "ю": "yu", "я": "ya",
}


def transliterate(text: str) -> str:
    return "".join(_TRANSLIT.get(ch, ch) for ch in (text or "").lower())


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", transliterate(text)).strip("-")


def _int(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    m = re.search(r"\d+", text.replace(" ", "").replace(" ", ""))
    return int(m.group(0)) if m else None


def _float(text: Optional[str]) -> Optional[float]:
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text.replace(" ", "").replace(" ", ""))
    return float(digits) if digits else None


# --- pure parsers (unit-tested against saved real fixtures) -----------------

def parse_listing(html: str) -> List[dict]:
    """Parse ``/novo-stroitelstvo`` into one base record per development card."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    out: List[dict] = []
    seen = set()
    for card in soup.select(".rh_prop_card"):
        a = card.find("a", href=True)
        if not a or "/сграда/" not in unquote(a["href"]):
            continue
        url = urljoin(BASE, a["href"])
        if url in seen:
            continue
        seen.add(url)

        h = card.find(["h2", "h3", "h4"])
        name = h.get_text(" ", strip=True) if h else None

        # card meta is rendered as "... | Етажи | 9 | Квадратура | 6800 | кв.м. | <type> | <price>"
        parts = [p.strip() for p in card.get_text("|", strip=True).split("|") if p.strip()]
        floors = area = None
        for i, p in enumerate(parts):
            low = p.lower()
            if low.startswith("етаж") and i + 1 < len(parts):
                floors = _int(parts[i + 1])
            elif low.startswith("квадрат") and i + 1 < len(parts):
                area = _float(parts[i + 1])
        joined = " ".join(parts).lower()
        materials = None  # not on the card
        out.append({
            "project_name": name,
            "url": url,
            "neighborhood": None,
            "neighborhood_slug": None,
            "developer_name": None,
            "price_eur_sqm": None,
            "akt_stage": None,
            "completion_year": None,
            "floors": floors,
            "materials": materials,
            "area_min_sqm": area,
            "area_max_sqm": area,
            "building_type": next((p for p in parts if "жилищ" in p.lower()
                                   or "комплекс" in p.lower() or "офис" in p.lower()), None),
            "price_on_request": "запитване" in joined,
        })
    return out


_AKT_RX = re.compile(r"\bакт\s*1?[456]\b", re.I)
_AKT_NUM_RX = re.compile(r"акт\s*(1?[456])", re.I)
_YEAR_RX = re.compile(r"\b(20[2-4]\d)\b")


def parse_detail(html: str) -> dict:
    """Best-effort enrichment from a ``/сграда/{slug}/`` detail page."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for s in soup(["script", "style"]):
        s.decompose()
    text = soup.get_text("\n", strip=True)

    def labelled(*labels) -> Optional[str]:
        for lab in labels:
            # "Label: value" or "Label\nvalue"
            m = re.search(rf"{lab}\s*[:\n]\s*([^\n]{{1,80}})", text, re.I)
            if m:
                v = m.group(1).strip(" :|").strip()
                if v and not re.fullmatch(r"[:\-–—]+", v):
                    return v
        return None

    nbhd = labelled("Квартал", "Район", "Локация", "Местоположение")
    developer = labelled("Инвеститор", "Строител", "Възложител")

    akt_stage = None
    completion_year = None
    makt = _AKT_NUM_RX.search(text)
    if makt:
        akt_stage = f"Акт {makt.group(1)}"
    # a completion year, ideally near "завършване"/"акт"
    mcompl = re.search(r"(?:завършване|въвеждане|акт)[^\n]{0,40}?(20[2-4]\d)", text, re.I)
    if mcompl:
        completion_year = int(mcompl.group(1))

    materials = labelled("Конструкция", "Строителство")

    return {
        "neighborhood": nbhd,
        "neighborhood_slug": _slug(nbhd) if nbhd else None,
        "developer_name": developer,
        "akt_stage": akt_stage,
        "completion_year": completion_year,
        "materials": materials,
    }


# --- scraper ----------------------------------------------------------------

class NovitesGradiScraper(BaseScraper):
    site = "novitesgradi"
    domain = "new_buildings"
    rate_limit_s = 1.5

    def __init__(self, scope: str = "sofia", enrich: bool = True,
                 max_listings: Optional[int] = None):
        super().__init__(scope)
        self.enrich = enrich
        self.max_listings = max_listings

    def scrape(self) -> Iterator[dict]:
        resp = self.get(f"{BASE}{LISTING}")
        cards = parse_listing(resp.text)
        if self.max_listings:
            cards = cards[: self.max_listings]
        self._log(f"{len(cards)} developments on the index")
        for rec in cards:
            if self.enrich and rec.get("url"):
                try:
                    d = parse_detail(self.get(rec["url"]).text)
                    for k, v in d.items():
                        if v is not None:
                            rec[k] = v
                except Exception as exc:  # noqa: BLE001 - enrichment is best-effort
                    self.stats.errors += 1
                    self._log(f"enrich failed {rec['url']}: {exc}")
            rec["source"] = self.site
            yield rec


SCRAPER = NovitesGradiScraper


def _cli() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="novitesgradi.bg Sofia new-build scraper")
    ap.add_argument("--city", default="sofia")
    ap.add_argument("--no-enrich", action="store_true", help="skip per-development detail pages")
    ap.add_argument("--max-listings", type=int, default=None)
    args = ap.parse_args()
    NovitesGradiScraper(args.city, enrich=not args.no_enrich,
                        max_listings=args.max_listings).run()


if __name__ == "__main__":
    _cli()
