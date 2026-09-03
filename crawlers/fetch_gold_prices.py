#!/usr/bin/env python3
"""
Gold price fetcher — BG Real Estate Intelligence Platform
=========================================================
Builds a monthly gold price series in **EUR per gram** for the "cost in gold"
affordability metric on the neighbourhood deep-dive page.

No single free source gives gold in EUR/gram with no API key, so we derive it:
  - Gold spot, USD per troy ounce, monthly  → datasets/gold-prices (datahub)
  - EUR/USD reference rate (USD per 1 EUR), daily → FRED DEXUSEU

    gold_eur_per_gram = (gold_usd_per_oz / usd_per_eur) / 31.1034768

EUR/USD only exists from 1999 (euro launch), so the series starts 1999-01.
Earlier years have no EUR gold price and are simply absent (the app shows "—").

Usage:
    python3 crawlers/fetch_gold_prices.py > data/raw/gold/gold_eur_per_gram.jsonl
"""

import json
import sys
from collections import defaultdict
from statistics import mean

import httpx

GOLD_USD_URL = "https://raw.githubusercontent.com/datasets/gold-prices/main/data/monthly.csv"
FX_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXUSEU"  # USD per EUR, daily
GRAMS_PER_TROY_OZ = 31.1034768


def fetch_csv(url: str) -> list[str]:
    resp = httpx.get(url, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    return resp.text.strip().splitlines()


def parse_gold_usd() -> dict[str, float]:
    """{'YYYY-MM': usd_per_oz} from the datahub monthly CSV (header: Date,Price)."""
    out: dict[str, float] = {}
    for line in fetch_csv(GOLD_USD_URL)[1:]:
        date_str, price = line.split(",")[:2]
        try:
            out[date_str.strip()] = float(price)
        except ValueError:
            continue
    return out


def parse_fx_monthly() -> dict[str, float]:
    """{'YYYY-MM': mean USD-per-EUR} from FRED daily DEXUSEU ('.' = missing)."""
    daily: dict[str, list[float]] = defaultdict(list)
    for line in fetch_csv(FX_URL)[1:]:
        date_str, val = line.split(",")[:2]
        if val.strip() in (".", ""):
            continue
        try:
            daily[date_str.strip()[:7]].append(float(val))  # YYYY-MM bucket
        except ValueError:
            continue
    return {ym: mean(vals) for ym, vals in daily.items() if vals}


def main() -> None:
    gold = parse_gold_usd()
    fx = parse_fx_monthly()
    rows = 0
    for ym in sorted(gold):
        if ym < "1999-01" or ym not in fx:
            continue
        eur_per_gram = (gold[ym] / fx[ym]) / GRAMS_PER_TROY_OZ
        print(json.dumps({
            "period_date": f"{ym}-01",
            "price_eur_per_gram": round(eur_per_gram, 4),
            "source": "datahub/gold-prices + FRED/DEXUSEU",
        }, ensure_ascii=False))
        rows += 1
    print(f"wrote {rows} monthly gold rows ({min(gold)}..{max(gold)} gold, EUR from 1999)",
          file=sys.stderr)


if __name__ == "__main__":
    main()
