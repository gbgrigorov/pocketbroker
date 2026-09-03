#!/usr/bin/env python3
"""
Bulgaria minimum monthly wage fetcher — BG Real Estate Intelligence Platform
============================================================================
For the "minimum salaries to buy" affordability metric. Source: Eurostat
`earn_mw_cur` (minimum wages), geo=BG, currency=EUR — authoritative, machine
readable, semiannual from 1999. We take the S1 (start-of-year) value as the
annual figure and derive BGN via the fixed euro peg (1 EUR = 1.95583 BGN).

Usage:
    python3 crawlers/fetch_min_wage.py > data/raw/macro/bg_min_wage.jsonl
"""

import json
import sys

import httpx

EUROSTAT_URL = (
    "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
    "earn_mw_cur?format=JSON&geo=BG&currency=EUR"
)
BGN_PER_EUR = 1.95583


def main() -> None:
    resp = httpx.get(EUROSTAT_URL, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    data = resp.json()

    time_index = data["dimension"]["time"]["category"]["index"]  # {'1999-S1': 0, ...}
    values = data["value"]                                       # {'0': 31.0, ...}

    rows = 0
    for period, idx in sorted(time_index.items(), key=lambda kv: kv[1]):
        if not period.endswith("-S1"):
            continue  # one value per year (January)
        amount_eur = values.get(str(idx))
        if amount_eur is None:
            continue
        year = int(period[:4])
        print(json.dumps({
            "year": year,
            "amount_eur": round(float(amount_eur), 2),
            "amount_bgn": round(float(amount_eur) * BGN_PER_EUR, 2),
            "source": "eurostat:earn_mw_cur",
        }, ensure_ascii=False))
        rows += 1
    print(f"wrote {rows} annual min-wage rows", file=sys.stderr)


if __name__ == "__main__":
    main()
