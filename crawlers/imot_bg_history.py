#!/usr/bin/env python3
"""
imot.bg Historical Price Scraper
=================================
Fetches one price snapshot per year (the date closest to Oct 15) from imot.bg's
historical archive:
  https://www.imot.bg/sredni-ceni/prodazhbi-sofiya?year=YYYY&date=D.M.YYYY

Confirmed page structure (from inspecting the live site):
  - Table class: sredni-ceni-2025 (always, regardless of year queried)
  - Header row 0: [Едностайни, Двустайни, Тристайни, Общо*]
  - Header row 1: [Район, Цена, €/кв.м, Цена, €/кв.м, Цена, €/кв.м, €/кв.м]
  - Data cols:    [name,   price, sqm,   price, sqm,   price, sqm,   overall_sqm]
  - NOTE: Historical pages have NO links on neighbourhood names (plain text only).
          Slugs are resolved later in the ETL step using Bulgarian name → slug mapping.

Usage:
    python3 imot_bg_history.py                                          # 1995-2025
    python3 imot_bg_history.py --start-year 2010 --end-year 2020
    python3 imot_bg_history.py --output-dir data/raw/imot_bg/sofia_history
    python3 imot_bg_history.py --start-year 2024 --end-year 2024       # test single year
"""

import asyncio
import argparse
import json
import re
import sys
from datetime import datetime, date
from typing import Optional
import pathlib

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://www.imot.bg"
BGN_PER_EUR = 1.95583

# Supported cities: imot.bg URL slug -> (english city key, Bulgarian name).
# Sofia's URL slug is "sofiya" but its data files use the "sofia" prefix.
CITIES = {
    "sofiya": ("sofia", "София"),
    "varna": ("varna", "Варна"),
    "burgas": ("burgas", "Бургас"),
    "plovdiv": ("plovdiv", "Пловдив"),
}


def history_url(transaction_type: str = "sale", city_slug: str = "sofiya") -> str:
    """Base archive URL for sales ('sale') or rentals ('rent') for a given city."""
    section = "naemi" if transaction_type == "rent" else "prodazhbi"
    return f"{BASE_URL}/sredni-ceni/{section}-{city_slug}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "bg,en;q=0.5",
}

# Normalise header names to standard property type keys
PROP_TYPE_NORMALISE = {
    "едностайни": "едностаен",
    "едностаен":  "едностаен",
    "студиа":     "едностаен",   # older pages used "Студиа"
    "двустайни":  "двустаен",
    "двустаен":   "двустаен",
    "тристайни":  "тристаен",
    "тристаен":   "тристаен",
}

MONTH_NAMES = {
    1: "january", 2: "february", 3: "march", 4: "april",
    5: "may", 6: "june", 7: "july", 8: "august",
    9: "september", 10: "october", 11: "november", 12: "december",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_price(text: str) -> Optional[float]:
    if not text:
        return None
    cleaned = (text.strip()
               .replace("\xa0", "")
               .replace(" ", "")
               .replace(" ", "")
               .replace(" ", "")
               .replace(",", ""))
    if cleaned in ("-", "", "—", "–"):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_date_bg(date_str: str) -> Optional[date]:
    """Parse D.M.YYYY (no leading zeros) → date. E.g. '3.10.2024' → date(2024,10,3)."""
    try:
        parts = date_str.strip().split(".")
        if len(parts) != 3:
            return None
        return date(int(parts[2]), int(parts[1]), int(parts[0]))
    except (ValueError, IndexError):
        return None


def pick_closest_date(dates: list[str], target_month: int, target_day: int) -> Optional[str]:
    """Return the D.M.YYYY string closest to target_month/target_day in the same year."""
    candidates = []
    for d_str in dates:
        d = parse_date_bg(d_str)
        if d is None:
            continue
        try:
            ref = date(d.year, target_month, target_day)
        except ValueError:
            continue
        diff = abs((d - ref).days)
        candidates.append((diff, d_str))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------

async def fetch_dates_for_year(client: httpx.AsyncClient, year: int, transaction_type: str = "sale",
                               city_slug: str = "sofiya") -> list[str]:
    """Return all available date strings (D.M.YYYY) for the given year from the dropdown."""
    try:
        resp = await client.get(history_url(transaction_type, city_slug),
                                params={"year": str(year)}, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"  [{year}] Error fetching date list: {e}", file=sys.stderr)
        return []

    html = resp.content.decode("windows-1251", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    date_sel = soup.find("select", {"name": "date"})
    if not date_sel:
        print(f"  [{year}] No date dropdown found — year may have no data", file=sys.stderr)
        return []
    return [opt.get("value", "") for opt in date_sel.find_all("option") if opt.get("value")]


async def fetch_snapshot(client: httpx.AsyncClient, year: int, date_str: str, transaction_type: str = "sale",
                         city_slug: str = "sofiya") -> list[dict]:
    """Fetch and parse the price table for a specific year + date string (D.M.YYYY)."""
    try:
        resp = await client.get(
            history_url(transaction_type, city_slug),
            params={"year": str(year), "date": date_str},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"  [{year}] Error fetching snapshot {date_str}: {e}", file=sys.stderr)
        return []

    html = resp.content.decode("windows-1251", errors="replace")
    soup = BeautifulSoup(html, "html.parser")

    # Table class is always "sredni-ceni-2025" regardless of the year parameter
    table = soup.find("table", class_="sredni-ceni-2025")
    if not table:
        # Fallback for potential future class name changes
        table = soup.find("table", class_=re.compile(r"sredni-ceni-\d+"))
    if not table:
        print(f"  [{year}] No price table found for date={date_str}", file=sys.stderr)
        return []

    # --- Parse column structure from header rows ---
    # Row 0: [Едностайни, Двустайни, Тристайни, Общо*]   ← property type names
    # Row 1: [Район, Цена, €/кв.м, Цена, €/кв.м, ...]   ← sub-headers (ignored)
    thead = table.find("thead")
    if not thead:
        print(f"  [{year}] No thead found", file=sys.stderr)
        return []

    header_rows = thead.find_all("tr")
    if not header_rows:
        return []

    # First header row → property type names (exclude "Общо*" aggregate column)
    first_row_headers = [th.get_text(strip=True) for th in header_rows[0].find_all("th")]
    prop_type_names = [
        PROP_TYPE_NORMALISE.get(h.lower(), h.lower())
        for h in first_row_headers
        if h and "общо" not in h.lower() and "€" not in h.lower()
    ]
    # Expected: ["едностаен", "двустаен", "тристаен"]

    if not prop_type_names:
        # Hardcoded fallback — standard 3-type layout
        prop_type_names = ["едностаен", "двустаен", "тристаен"]

    # Column mapping: type[i] uses data columns (1 + i*2) for price and (2 + i*2) for sqm
    prop_type_cols: list[tuple[str, int, int]] = [
        (name, 1 + i * 2, 2 + i * 2) for i, name in enumerate(prop_type_names)
    ]
    # Overall average is in the last data column
    overall_col = 1 + len(prop_type_names) * 2   # = 7 for 3 types

    # --- Parse data rows ---
    scraped_at = datetime.utcnow().isoformat() + "Z"
    snapshot_dt = parse_date_bg(date_str)
    period_date = snapshot_dt.isoformat() if snapshot_dt else date_str
    city_key = CITIES[city_slug][0]

    records: list[dict] = []

    for row in table.select("tbody tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue

        # Historical pages: neighbourhood name is plain text (no anchor link)
        neighbourhood = cells[0].get_text(strip=True)
        if not neighbourhood:
            continue

        overall_sqm = (
            parse_price(cells[overall_col].get_text())
            if overall_col < len(cells)
            else None
        )

        for prop_type, price_col, sqm_col in prop_type_cols:
            price_eur = parse_price(cells[price_col].get_text()) if price_col < len(cells) else None
            sqm_eur = parse_price(cells[sqm_col].get_text()) if sqm_col < len(cells) else None

            if price_eur is None and sqm_eur is None:
                continue

            price_bgn = round(price_eur * BGN_PER_EUR, 2) if price_eur is not None else None
            sqm_bgn = round(sqm_eur * BGN_PER_EUR, 2) if sqm_eur is not None else None

            records.append({
                "source": "imot.bg",
                "city": city_key,
                "city_slug": city_slug,
                "year": year,
                "snapshot_date": date_str,
                "period_date": period_date,
                "neighborhood": neighbourhood,
                # No slug on historical pages — ETL resolves using Bulgarian name lookup
                "neighborhood_slug": None,
                "property_type": prop_type,
                "transaction_type": transaction_type,
                "price_eur": price_eur,
                "price_bgn": price_bgn,
                "price_eur_sqm": sqm_eur,
                "price_bgn_sqm": sqm_bgn,
                "overall_avg_eur_sqm": overall_sqm,
                "scraped_at": scraped_at,
            })

    return records


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

async def run(
    start_year: int,
    end_year: int,
    target_month: int,
    target_day: int,
    output_dir: Optional[str],
    transaction_type: str = "sale",
    city_slug: str = "sofiya",
) -> None:
    if output_dir:
        pathlib.Path(output_dir).mkdir(parents=True, exist_ok=True)

    month_name = MONTH_NAMES.get(target_month, f"month{target_month:02d}")
    total_years = end_year - start_year + 1
    success = 0

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        for i, year in enumerate(range(start_year, end_year + 1), 1):
            print(f"[{i}/{total_years}] Year {year}: fetching date list...", file=sys.stderr)

            dates = await fetch_dates_for_year(client, year, transaction_type, city_slug)
            if not dates:
                print(f"  [{year}] No dates — skipping", file=sys.stderr)
                await asyncio.sleep(1.0)
                continue

            chosen = pick_closest_date(dates, target_month, target_day)
            if not chosen:
                print(f"  [{year}] No date near {target_day}/{target_month} — skipping", file=sys.stderr)
                continue

            target_str = f"{target_day}.{target_month}.{year}"
            print(f"  [{year}] Using {chosen} (closest to {target_str})", file=sys.stderr)
            await asyncio.sleep(0.8)

            records = await fetch_snapshot(client, year, chosen, transaction_type, city_slug)
            print(f"  [{year}] {len(records)} records", file=sys.stderr)

            if records:
                if output_dir:
                    out_path = pathlib.Path(output_dir) / f"{year}_{month_name}.jsonl"
                    with open(out_path, "w", encoding="utf-8") as f:
                        for rec in records:
                            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    print(f"  [{year}] Saved → {out_path}", file=sys.stderr)
                else:
                    for rec in records:
                        print(json.dumps(rec, ensure_ascii=False))
                success += 1

            await asyncio.sleep(1.2)  # polite delay

    print(f"\nDone. {success}/{total_years} years scraped successfully.", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="imot.bg historical price scraper — one October snapshot per year (1995–2025)"
    )
    parser.add_argument("--start-year", type=int, default=1995)
    parser.add_argument("--end-year",   type=int, default=2025)
    parser.add_argument("--target-month", type=int, default=10, help="Month to target (default: 10 = October)")
    parser.add_argument("--target-day",   type=int, default=15, help="Day to aim for (default: 15)")
    parser.add_argument(
        "--output-dir", type=str, default=None,
        help="Write one .jsonl per year here (default: stdout)",
    )
    parser.add_argument("--transaction-type", choices=["sale", "rent"], default="sale")
    parser.add_argument("--city", choices=list(CITIES), default="sofiya",
                        help="imot.bg city URL slug (default: sofiya)")
    args = parser.parse_args()
    asyncio.run(run(args.start_year, args.end_year, args.target_month, args.target_day,
                    args.output_dir, args.transaction_type, args.city))


if __name__ == "__main__":
    main()
