"""Phase-3.5 ETL: raw Papagal ownership edges + telemetry -> DB.

    cd backend && .venv/bin/python -m etl.run_phase35
    cd backend && .venv/bin/python -m etl.run_phase35 --backfill-stubs

Idempotent: companies upsert on ЕИК, persons on ``person_key``, edges on their
natural key. Run *after* the builders exist (so their entities are reused, not
duplicated). Provenance (``source``) is carried onto every node and edge.

``--backfill-stubs`` directly scrapes every stub company (depth-2/3 expansion
left it as a name+ЕИК-only node — only a company's own Papagal page has
capital/address). Opt-in: with hundreds of stubs this is a long scrape, so it
never runs implicitly as a side effect of the routine jsonl-load pass.

Inputs (produced by ``crawlers/scraper_kit/sites/papagal.py``):
    data/raw/ownership/<scope>/papagal_<date>.jsonl
    data/raw/ownership/<scope>/papagal_<date>.stats.json   (crawl telemetry)
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.models import City
from etl.entities import (
    OwnershipReport,
    backfill_stub_companies,
    derive_insolvency_flags,
    load_ownership,
)
from etl.load_phase3 import Phase3Report, load_crawl_runs

DATA_ROOT = Path(__file__).resolve().parents[2] / "data"


def _load_jsonl(path: str):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--backfill-stubs", action="store_true",
                         help="directly scrape every stub company (no capital/address yet)")
    args = parser.parse_args()

    report = OwnershipReport()
    session = SessionLocal()
    try:
        for path in sorted(glob.glob(str(DATA_ROOT / "raw" / "ownership" / "**" / "*.jsonl"),
                                     recursive=True)):
            load_ownership(session, _load_jsonl(path), report)

        # Crawl telemetry for the headline /api/stats counter.
        city_slug_to_id = {slug: cid for cid, slug in session.execute(select(City.id, City.slug))}
        manifests = [
            json.loads(Path(p).read_text(encoding="utf-8"))
            for p in glob.glob(str(DATA_ROOT / "raw" / "ownership" / "**" / "*.stats.json"),
                               recursive=True)
        ]
        load_crawl_runs(session, manifests, city_slug_to_id, Phase3Report())

        flagged = derive_insolvency_flags(session)
        print(f"insolvency flags derived/updated: {flagged}")
        session.commit()

        if args.backfill_stubs:
            backfill = backfill_stub_companies(session)
            if backfill["stubs_found"]:
                print(f"stub companies found: {backfill['stubs_found']}, "
                      f"backfilled via direct scrape: {backfill['scraped']}")
                session.commit()
    finally:
        session.close()

    print("=== Phase-3.5 ownership ETL report ===")
    print(f"companies created: {report.companies_created}")
    print(f"persons created:   {report.persons_created}")
    print(f"edges upserted:    {report.edges_upserted}")


if __name__ == "__main__":
    main()
