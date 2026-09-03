#!/usr/bin/env python3
"""
imot.bg Average Price Scraper — BG Real Estate Intelligence Platform
=====================================================================

Scrapes the price table from https://www.imot.bg/sredni-ceni

KEY FINDING (2026-05-24):
  The main /sredni-ceni page contains a single <table class="sredni-ceni-2025">
  with ALL Sofia neighborhoods in one request. No need to hit individual
  neighborhood pages for basic per-type prices.

  The page also embeds a JavaScript object `raioniAvgPrice` with an overall
  EUR/sqm average per neighborhood — useful as a quick sanity check.

Table structure:
  Columns: Район | Едностайни Цена | €/кв.м | Двустайни Цена | €/кв.м |
           Тристайни Цена | €/кв.м | Общо €/кв.м

Output: JSON lines to stdout, one record per (neighborhood, property_type).

Usage:
  python3 bg-realestate/crawlers/imot_prices.py
  python3 bg-realestate/crawlers/imot_prices.py 2>&1 | head -50
"""

import argparse
import asyncio
import json
import logging
import re
import sys
from datetime import date, datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = "https://www.imot.bg"
SREDNI_CENI_URL = f"{BASE_URL}/sredni-ceni"

# Supported cities: imot.bg URL slug -> (english city key, Bulgarian name).
# Sofia's URL slug is "sofiya" but its data files use the "sofia" prefix.
CITIES = {
    "sofiya": ("sofia", "София"),
    "varna": ("varna", "Варна"),
    "burgas": ("burgas", "Бургас"),
    "plovdiv": ("plovdiv", "Пловдив"),
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; BG-RE-Research/1.0; +https://github.com/bg-realestate)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "bg,en;q=0.5",
}

# BGN/EUR fixed rate (Bulgaria pegged since 1999)
BGN_PER_EUR = 1.95583

# Property type column mapping (0-indexed within the 8 columns)
# Columns: 0=Район, 1=1-ст цена, 2=1-ст €/кв.м, 3=2-ст цена, 4=2-ст €/кв.м,
#          5=3-ст цена, 6=3-ст €/кв.м, 7=Общо €/кв.м
PROPERTY_TYPES = [
    ("едностаен", 1, 2),   # (bg_name, price_col, sqm_col)
    ("двустаен",  3, 4),
    ("тристаен",  5, 6),
]

# ---------------------------------------------------------------------------
# Sofia neighborhood slugs (from href attributes on /sredni-ceni)
# Used for validation and targeted individual-page scraping if needed.
# The main scraper uses the full table on /sredni-ceni directly.
# ---------------------------------------------------------------------------

SOFIA_NEIGHBORHOODS = [
    "lozenets",
    "mladost-1",
    "mladost-2",
    "mladost-3",
    "mladost-4",
    "vitosha",
    "manastirski-livadi",
    "studentski-grad",
    "lyulin-tsentar",
    "lyulin-1",
    "lyulin-2",
    "lyulin-3",
    "lyulin-4",
    "lyulin-5",
    "lyulin-6",
    "lyulin-7",
    "lyulin-8",
    "lyulin-9",
    "lyulin-10",
    "borovo",
    "boyana",
    "dragalevtsi",
    "simeonovo",
    "krastova-vada",
    "iztok",
    "izgrev",
    "ivan-vazov",
    "oborishte",
    "tsentar",
    "yavorov",
    "geo-milev",
    "gotse-delchev",
    "musagenitsa",
    "strelbishte",
    "krasno-selo",
    "hipodruma",
    "hladilnika",
    "lagera",
    "banishora",
    "slatina",
    "druzhba-1",
    "druzhba-2",
    "darvenitsa",
    "nadezhda-1",
    "nadezhda-2",
    "nadezhda-3",
    "nadezhda-4",
    "ovcha-kupel",
    "ovcha-kupel-1",
    "ovcha-kupel-2",
    "belite-brezi",
    "malinova-dolina",
    "gorublyane",
    "dianabad",
    "reduta",
    "pavlovo",
    "knyazhevo",
    "gorna-banya",
    "levski",
    "zapaden-park",
    "svoboda",
    "poduyane",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def parse_price(text: str) -> Optional[float]:
    """Parse a price string like '4 754' or '4,754' or '-' into a float."""
    if not text:
        return None
    cleaned = text.strip().replace("\xa0", "").replace(" ", "").replace(",", "")
    if cleaned == "-" or not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def extract_slug(href: str) -> Optional[str]:
    """Extract the neighborhood slug from an href like //www.imot.bg/sredni-ceni/prodazhbi-sofiya/lozenets"""
    if not href:
        return None
    match = re.search(r"/(?:prodazhbi|naemi)-([^/]+)/([^?\"#]+)", href)
    if match:
        return match.group(2)
    return None


def extract_name_to_slug(soup: BeautifulSoup) -> dict[str, str]:
    """Build a mapping of Bulgarian neighborhood name → URL slug from the table."""
    mapping: dict[str, str] = {}
    table = soup.find("table", class_="sredni-ceni-2025")
    if not table:
        return mapping
    for a_tag in table.select("td:first-child a"):
        name = a_tag.get_text(strip=True)
        slug = extract_slug(a_tag.get("href", ""))
        if name and slug:
            mapping[name] = slug
    return mapping


# ---------------------------------------------------------------------------
# Main scrape logic — single-page approach (efficient)
# ---------------------------------------------------------------------------

async def fetch_main_table(
    client: httpx.AsyncClient,
    transaction_type: str = "sale",
    city_slug: str = "sofiya",
) -> list[dict]:
    """
    Fetch the sredni-ceni table for sales ('sale') or rentals ('rent') in one request.
    Returns a list of price records (one per neighborhood × property_type).
    """
    city_key, city_name = CITIES[city_slug]
    section = "prodazhbi" if transaction_type == "sale" else "naemi"
    url = f"{BASE_URL}/sredni-ceni/{section}-{city_slug}"
    log.info("Fetching %s (%s)", url, transaction_type)
    try:
        resp = await client.get(url)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        log.error("HTTP error fetching main page: %s", exc)
        return []
    except httpx.RequestError as exc:
        log.error("Request error fetching main page: %s", exc)
        return []

    # imot.bg uses windows-1251 encoding
    html = resp.content.decode("windows-1251", errors="replace")
    soup = BeautifulSoup(html, "html.parser")

    table = soup.find("table", class_="sredni-ceni-2025")
    if not table:
        log.error("Price table not found on page — site structure may have changed")
        return []

    # Also extract the raioniAvgPrice JS object for the overall €/sqm
    avg_price_js: dict[str, float] = {}
    js_match = re.search(r"raioniAvgPrice\s*=\s*(\{[^;]+\})", html)
    if js_match:
        # Convert single-quoted JS object to valid JSON
        js_obj = js_match.group(1)
        js_obj_json = js_obj.replace("'", '"')
        try:
            avg_price_js = json.loads(js_obj_json)
        except json.JSONDecodeError as exc:
            log.warning("Could not parse raioniAvgPrice JS object: %s", exc)

    scraped_at = datetime.utcnow().isoformat() + "Z"
    period_date = date.today().replace(day=1).isoformat()  # first of current month

    records: list[dict] = []
    rows = table.select("tbody tr")
    log.info("Found %d neighborhood rows in table", len(rows))

    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 8:
            continue

        # Column 0: neighborhood name + href with slug
        name_link = cells[0].find("a")
        if not name_link:
            continue
        neighborhood_name = name_link.get_text(strip=True)
        slug = extract_slug(name_link.get("href", ""))
        if not slug:
            log.warning("Could not extract slug for neighborhood: %s", neighborhood_name)
            continue

        # Column 7: overall average EUR/sqm (cross-check vs raioniAvgPrice)
        overall_sqm = parse_price(cells[7].get_text())

        # Per-type prices
        for prop_type, price_col, sqm_col in PROPERTY_TYPES:
            price_eur = parse_price(cells[price_col].get_text())
            sqm_eur = parse_price(cells[sqm_col].get_text())

            if price_eur is None and sqm_eur is None:
                # No data for this property type in this neighborhood — skip
                continue

            price_bgn = round(price_eur * BGN_PER_EUR, 2) if price_eur is not None else None
            sqm_bgn = round(sqm_eur * BGN_PER_EUR, 2) if sqm_eur is not None else None

            record = {
                "source": "imot.bg",
                "city": city_key,
                "city_slug": city_slug,
                "neighborhood": neighborhood_name,
                "neighborhood_slug": slug,
                "property_type": prop_type,
                "transaction_type": transaction_type,
                "price_eur": price_eur,
                "price_bgn": price_bgn,
                "price_eur_sqm": sqm_eur,
                "price_bgn_sqm": sqm_bgn,
                "overall_avg_eur_sqm": overall_sqm,
                "period_date": period_date,
                "period_type": "monthly",
                "scraped_at": scraped_at,
            }
            records.append(record)

    log.info("Extracted %d price records total", len(records))
    return records


# ---------------------------------------------------------------------------
# Optional: per-neighborhood individual page scraper
# (Use when you need more detailed data from the listing page)
# ---------------------------------------------------------------------------

async def fetch_neighborhood_page(
    client: httpx.AsyncClient,
    city_slug: str,
    neighborhood_slug: str,
    property_type: Optional[str] = None,
) -> dict:
    """
    Fetch an individual neighborhood page for supplementary data.
    The main table on /sredni-ceni has the core price data already.

    Args:
        property_type: optional pt= param ('1'=едностаен, '2'=двустаен, '3'=тристаен)
    """
    url = f"{BASE_URL}/sredni-ceni/prodazhbi-{city_slug}/{neighborhood_slug}"
    if property_type:
        url += f"?pt={property_type}"

    log.info("Fetching neighborhood page: %s", url)
    try:
        resp = await client.get(url)
        if resp.status_code == 404:
            log.warning("404 for %s — skipping", url)
            return {"url": url, "status": 404, "data": None}
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        log.error("HTTP %s for %s", exc.response.status_code, url)
        return {"url": url, "status": exc.response.status_code, "data": None}
    except httpx.RequestError as exc:
        log.error("Request error for %s: %s", url, exc)
        return {"url": url, "status": None, "data": None}

    html = resp.content.decode("windows-1251", errors="replace")
    # Extract sample count (number of listings shown) from title or content
    sample_match = re.search(r"(\d+)\s+(?:обяви|оферти)", html)
    sample_count = int(sample_match.group(1)) if sample_match else None

    await asyncio.sleep(1.5)  # polite delay between individual page requests

    return {
        "url": url,
        "status": resp.status_code,
        "sample_count": sample_count,
    }


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

async def main(transaction_type: str = "sale", city_slug: str = "sofiya"):
    """Crawl all neighborhoods of a city from the main sredni-ceni table and print as JSON lines."""
    log.info("Starting imot.bg price scraper (%s, %s)", city_slug, transaction_type)

    async with httpx.AsyncClient(
        headers=HEADERS,
        follow_redirects=True,
        timeout=30.0,
    ) as client:
        records = await fetch_main_table(client, transaction_type, city_slug)

    if not records:
        log.error("No records scraped — check errors above")
        sys.exit(1)

    for record in records:
        print(json.dumps(record, ensure_ascii=False))

    log.info("Done. %d records printed.", len(records))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="imot.bg current sredni-ceni scraper")
    parser.add_argument("--transaction-type", choices=["sale", "rent"], default="sale")
    parser.add_argument("--city", choices=list(CITIES), default="sofiya",
                        help="imot.bg city URL slug (default: sofiya)")
    args = parser.parse_args()
    asyncio.run(main(args.transaction_type, args.city))
