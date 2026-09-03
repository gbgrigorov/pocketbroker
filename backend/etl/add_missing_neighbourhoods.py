"""Incrementally add newly-mapped neighbourhoods to an already-loaded DB.

Unlike ``run_etl --reset`` (which wipes and reloads everything), this is
non-destructive: it inserts only the neighbourhoods that now have coordinates but
are not yet in the database, plus their price rows. Existing neighbourhood rows —
and therefore the new_building / metro foreign keys that reference them — are left
completely untouched.

    cd backend && .venv/bin/python -m etl.add_missing_neighbourhoods [--dry-run]
"""

from __future__ import annotations

import argparse
import glob
import json

from sqlalchemy import select

from app.db import SessionLocal
from app.models import City, Neighbourhood, PriceSnapshot
from etl.build_registry import (COORDS, CURRENT, CURRENT_RENT_GLOB, HISTORY_GLOB,
                                 HISTORY_RENT_GLOB, load_jsonl)
from etl.load import _price_snapshot
from etl.neighbourhoods import NameResolver, build_canonical_registry


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be inserted, commit nothing")
    args = parser.parse_args()

    # Canonical registry from sale + rent snapshots ∩ coords.
    current_records = list(load_jsonl(CURRENT))
    for p in sorted(glob.glob(CURRENT_RENT_GLOB)):
        current_records += list(load_jsonl(p))
    with open(COORDS, encoding="utf-8") as fh:
        coords = json.load(fh)
    registry = build_canonical_registry(current_records, coords)
    resolver = NameResolver({e["name"]: s for s, e in registry.items()})

    history_records = [r for p in sorted(glob.glob(HISTORY_GLOB)) for r in load_jsonl(p)]
    for p in sorted(glob.glob(HISTORY_RENT_GLOB)):
        history_records += list(load_jsonl(p))

    session = SessionLocal()
    try:
        city = session.scalar(select(City).where(City.slug == "sofia"))
        if city is None:
            raise SystemExit("No Sofia city row — run the full ETL first.")

        existing = {n.slug: n.id for n in session.scalars(select(Neighbourhood)).all()}
        new_slugs = [s for s in registry if s not in existing]
        print(f"registry: {len(registry)} | already in DB: {len(existing)} | "
              f"to add: {len(new_slugs)}")
        if not new_slugs:
            print("Nothing to add — DB already current.")
            return

        # Insert the new neighbourhood rows.
        slug_to_id = dict(existing)
        for slug in new_slugs:
            entry = registry[slug]
            n = Neighbourhood(
                city_id=city.id, name=entry["name"], slug=entry["slug"],
                lat=entry.get("lat"), lon=entry.get("lon"),
                coord_source=entry.get("coord_source"),
            )
            session.add(n)
            session.flush()
            slug_to_id[slug] = n.id

        # Price rows for the new neighbourhoods only (existing rows untouched).
        new_id_set = {slug_to_id[s] for s in new_slugs}
        current_added = 0
        for rec in current_records:
            nid = slug_to_id.get(rec.get("neighborhood_slug"))
            if nid in new_id_set:
                session.add(_price_snapshot(nid, rec))
                current_added += 1

        history_added = 0
        for rec in history_records:
            slug = resolver.resolve(rec.get("neighborhood"))
            nid = slug_to_id.get(slug) if slug else None
            if nid in new_id_set:
                session.add(_price_snapshot(nid, rec))
                history_added += 1

        print(f"new neighbourhoods: {len(new_slugs)}")
        print(f"current price rows added:    {current_added}")
        print(f"historical price rows added: {history_added}")

        if args.dry_run:
            session.rollback()
            print("dry-run: rolled back, nothing committed.")
        else:
            session.commit()
            print("committed.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
