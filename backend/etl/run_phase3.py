"""Run the Phase-3 ETL: normalized builders + new buildings + crawl telemetry -> DB.

    cd backend && .venv/bin/python -m etl.run_phase3

Idempotent: upserts on natural keys, safe to run on a schedule. Requires the
price ETL to have populated ``city``/``neighbourhood`` first (FKs).

Inputs (produced by the scrapers + normalizers):
    data/normalized/builders/*.jsonl
    data/normalized/new_buildings/<city>.jsonl
    data/raw/**/*.stats.json        (crawl run manifests)
"""

from __future__ import annotations

import glob
import json
import os
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.models import City
from etl.load_phase3 import (Phase3Report, load_builders, load_crawl_runs,
                             load_new_buildings)

DATA_ROOT = Path(__file__).resolve().parents[2] / "data"


def _load_jsonl(path: str):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def main() -> None:
    report = Phase3Report()
    session = SessionLocal()
    try:
        # 1. Builders (national) — load first so projects can link to them.
        for path in sorted(glob.glob(str(DATA_ROOT / "normalized" / "builders" / "*.jsonl"))):
            load_builders(session, _load_jsonl(path), report)

        # 2. New buildings, per city (filename stem = city slug).
        for path in sorted(glob.glob(str(DATA_ROOT / "normalized" / "new_buildings" / "*.jsonl"))):
            city_slug = Path(path).stem
            load_new_buildings(session, _load_jsonl(path), city_slug, report)

        # 3. Crawl telemetry from every per-run manifest.
        city_slug_to_id = {slug: cid for cid, slug in session.execute(select(City.id, City.slug))}
        manifests = [
            json.loads(Path(p).read_text(encoding="utf-8"))
            for p in glob.glob(str(DATA_ROOT / "raw" / "**" / "*.stats.json"), recursive=True)
        ]
        load_crawl_runs(session, manifests, city_slug_to_id, report)

        session.commit()
    finally:
        session.close()

    print("=== Phase-3 ETL report ===")
    print(f"builders upserted:           {report.builders_upserted}")
    print(f"new buildings upserted:      {report.new_buildings_upserted}")
    print(f"new-building source rows:    {report.new_building_sources}")
    print(f"projects linked to builder:  {report.projects_linked_to_builder}")
    print(f"crawl runs loaded/skipped:   {report.crawl_runs_loaded}/{report.crawl_runs_skipped}")


if __name__ == "__main__":
    main()
