"""Run the full ETL against the configured database (DATABASE_URL).

    cd backend && .venv/bin/python -m etl.run_etl [--reset]

Builds the canonical registry from raw data, then loads city + the 62 mapped
neighbourhoods + all resolvable price rows. Prints a conservation report.
"""

from __future__ import annotations

import argparse
import glob
import json
import os

from sqlalchemy import delete, func, select

from app.db import SessionLocal
from app.models import (City, GoldPrice, MinWage, Neighbourhood, NeighbourhoodMetro,
                        PriceSnapshot)
from etl.build_registry import (COORDS, CURRENT, CURRENT_RENT_GLOB, GOLD, HISTORY_GLOB,
                                 HISTORY_RENT_GLOB, MIN_WAGE, load_jsonl)
from etl.load import load_all
from etl.neighbourhoods import NameResolver, build_canonical_registry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="delete existing rows before loading")
    args = parser.parse_args()

    # The current sale + rent snapshots together define the canonical registry:
    # any priced slug with a coordinate is mappable (rent-only names included).
    current_records = list(load_jsonl(CURRENT))
    for p in sorted(glob.glob(CURRENT_RENT_GLOB)):
        current_records += list(load_jsonl(p))
    with open(COORDS, encoding="utf-8") as fh:
        coords = json.load(fh)
    registry = build_canonical_registry(current_records, coords)
    resolver = NameResolver({e["name"]: s for s, e in registry.items()})
    # Rent rows ride through the same loader (tagged transaction_type='rent').
    history_records = [r for p in sorted(glob.glob(HISTORY_GLOB)) for r in load_jsonl(p)]
    for p in sorted(glob.glob(HISTORY_RENT_GLOB)):
        history_records += list(load_jsonl(p))

    # Reference series (optional files)
    gold_records = list(load_jsonl(GOLD)) if os.path.exists(GOLD) else []
    min_wage_records = list(load_jsonl(MIN_WAGE)) if os.path.exists(MIN_WAGE) else []

    session = SessionLocal()
    try:
        existing = session.scalar(select(func.count()).select_from(City))
        if existing and not args.reset:
            raise SystemExit("Database already has data. Re-run with --reset to reload.")
        if args.reset:
            for model in (NeighbourhoodMetro, PriceSnapshot, Neighbourhood, City,
                          GoldPrice, MinWage):
                session.execute(delete(model))
            session.commit()

        report = load_all(
            session,
            registry=registry,
            current_records=current_records,
            history_records=history_records,
            resolver=resolver,
            gold_records=gold_records,
            min_wage_records=min_wage_records,
        )
    finally:
        session.close()

    print("=== ETL report ===")
    print(f"neighbourhoods loaded: {report.neighbourhoods_loaded}")
    print(f"current:  loaded {report.current_loaded}, skipped {report.current_skipped} "
          f"(of {len(current_records)})")
    print(f"history:  loaded {report.history_loaded}, skipped {report.history_skipped} "
          f"(of {len(history_records)})")
    print(f"total price rows loaded: {report.current_loaded + report.history_loaded}")
    print(f"gold rows: {report.gold_loaded}, min-wage rows: {report.min_wage_loaded}")
    # conservation assertions — fail loudly rather than drop silently
    assert report.current_loaded + report.current_skipped == len(current_records)
    assert report.history_loaded + report.history_skipped == len(history_records)
    assert report.gold_loaded == len(gold_records)
    assert report.min_wage_loaded == len(min_wage_records)
    print("conservation OK: every input row accounted for")


if __name__ == "__main__":
    main()
