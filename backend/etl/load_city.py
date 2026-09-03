"""Incrementally load an additional city (Varna / Burgas / Plovdiv) into the DB.

Non-destructive, in the spirit of ``add_missing_neighbourhoods.py``: it creates
the city's ``City`` row (if absent), inserts that city's neighbourhoods, and loads
their current (sale+rent) + historical (sale+rent) price rows. Existing rows —
Sofia and its new_building / metro foreign keys — are never touched.

Slugs are unique only *within* a city (migration ``b2c3d4e5f6a7``), so every
lookup here is keyed by ``(city_id, slug)``, never by the bare slug.

    cd backend && .venv/bin/python -m etl.load_city --city varna [--dry-run]
"""

from __future__ import annotations

import argparse
import glob
import json

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import City, Neighbourhood
from etl.build_registry import CITIES, load_jsonl
from etl.load import _price_snapshot
from etl.neighbourhoods import NameResolver, build_canonical_registry


def _load_glob(pattern: str) -> list[dict]:
    return [rec for path in sorted(glob.glob(pattern)) for rec in load_jsonl(path)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Load one additional city into the DB")
    parser.add_argument("--city", choices=list(CITIES), required=True)
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be inserted, commit nothing")
    args = parser.parse_args()
    cfg = CITIES[args.city]

    # Current sale + rent snapshots define the canonical registry (priced ∩ coords).
    current_records = _load_glob(cfg["current_glob"]) + _load_glob(cfg["current_rent_glob"])
    with open(cfg["coords"], encoding="utf-8") as fh:
        coords = json.load(fh)
    registry = build_canonical_registry(current_records, coords)
    resolver = NameResolver({e["name"]: s for s, e in registry.items()})

    history_records = _load_glob(cfg["history_glob"]) + _load_glob(cfg["history_rent_glob"])

    print(f"[{args.city}] current rows: {len(current_records)} | history rows: "
          f"{len(history_records)} | coords: {len(coords)} | "
          f"canonical (price∩coord): {len(registry)}")

    session = SessionLocal()
    try:
        city = session.scalar(select(City).where(City.slug == args.city))
        if city is None:
            city = City(name=cfg["name"], slug=args.city)
            session.add(city)
            session.flush()
            print(f"[{args.city}] created city row id={city.id}")
        else:
            print(f"[{args.city}] city already exists id={city.id} — adding only new neighbourhoods")

        # Existing neighbourhoods for THIS city only, keyed by slug.
        existing = {
            n.slug: n.id
            for n in session.scalars(
                select(Neighbourhood).where(Neighbourhood.city_id == city.id)
            ).all()
        }
        new_slugs = [s for s in registry if s not in existing]
        print(f"[{args.city}] registry {len(registry)} | already in DB {len(existing)} | "
              f"to add {len(new_slugs)}")

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

        # Price rows for the newly-added neighbourhoods only (existing rows untouched).
        new_id_set = {slug_to_id[s] for s in new_slugs}

        current_loaded = current_skipped = 0
        for rec in current_records:
            nid = slug_to_id.get(rec.get("neighborhood_slug"))
            if nid in new_id_set:
                session.add(_price_snapshot(nid, rec))
                current_loaded += 1
            else:
                current_skipped += 1

        history_loaded = history_skipped = 0
        for rec in history_records:
            slug = resolver.resolve(rec.get("neighborhood"))
            nid = slug_to_id.get(slug) if slug else None
            if nid in new_id_set:
                session.add(_price_snapshot(nid, rec))
                history_loaded += 1
            else:
                history_skipped += 1

        print(f"[{args.city}] neighbourhoods added: {len(new_slugs)}")
        print(f"[{args.city}] current: loaded {current_loaded}, skipped {current_skipped} "
              f"(of {len(current_records)})")
        print(f"[{args.city}] history: loaded {history_loaded}, skipped {history_skipped} "
              f"(of {len(history_records)})")
        # Conservation: account for every input row.
        assert current_loaded + current_skipped == len(current_records)
        assert history_loaded + history_skipped == len(history_records)
        print(f"[{args.city}] conservation OK: every input row accounted for")

        if args.dry_run:
            session.rollback()
            print(f"[{args.city}] dry-run: rolled back, nothing committed.")
        else:
            session.commit()
            total = session.scalar(
                select(func.count()).select_from(Neighbourhood).where(
                    Neighbourhood.city_id == city.id
                )
            )
            print(f"[{args.city}] committed. neighbourhoods now in DB for this city: {total}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
