#!/usr/bin/env python3
"""Aggregate citizen-sensor PM2.5 into per-neighbourhood seasonal averages.

Reads the Sensor.Community JSONL (one row per sensor per year per season) and
collapses it to the viz-ready ``neighbourhood_air`` table: for each neighbourhood,
year and season, the mean PM2.5 of *all* sensors that fall within it. Averaging
many cheap SDS011 sensors cancels their individual noise — far more robust than
mapping a neighbourhood to a single nearest sensor.

    sc_sofia_<year>.jsonl  →  neighbourhood_air(neighbourhood_id, year, season,
                                                pm25_avg, aqi_avg, sensor_count)

Usage:
    cd backend && python3 ../crawlers/etl_neighbourhood_air.py
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent))  # for pm25_to_aqi

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from app.db import DATABASE_URL
from app.models import City, Neighbourhood, NeighbourhoodAir
from fetch_air_quality import pm25_to_aqi

# A sensor is counted toward the nearest neighbourhood centroid within this radius.
# Sofia neighbourhoods are ~1–2 km across; 2 km keeps sensors with their area while
# dropping ones out in the periphery with no nearby centroid.
MAX_ASSIGN_M = 2000

# Plausibility cap on a single sensor's *seasonal-mean* PM2.5 (µg/m³). The crawler's
# per-reading filter (≤1000) lets a stuck-high SDS011 through with an absurd seasonal
# mean (e.g. 999.9), which then poisons the neighbourhood average — worst when the
# area has only that one sensor. Even Sofia's most polluted neighbourhoods top out
# around a ~80–90 seasonal mean in the heating season, so a sensor-season above this
# is a fault, not real air. Dropping it here needs no re-crawl, just an ETL re-run.
PM25_SEASONAL_MAX = 150.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    dφ = math.radians(lat2 - lat1)
    dλ = math.radians(lon2 - lon1)
    a = math.sin(dφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(dλ / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def nearest_neighbourhood(lat: float, lon: float, neighbourhoods: list) -> int | None:
    """Id of the nearest neighbourhood centroid within MAX_ASSIGN_M, else None."""
    best: tuple | None = None  # (distance, id)
    for n in neighbourhoods:
        if n.lat is None or n.lon is None:
            continue
        d = haversine_m(lat, lon, float(n.lat), float(n.lon))
        if d <= MAX_ASSIGN_M and (best is None or d < best[0]):
            best = (d, n.id)
    return best[1] if best else None


def aggregate(session: Session, data_dir: Path, city_slug: str = "sofia") -> None:
    """Read sc_<city>_*.jsonl, average per (neighbourhood, year, season), upsert."""
    neighbourhoods = session.scalars(
        select(Neighbourhood).join(City).where(City.slug == city_slug)
    ).all()

    # (neighbourhood_id, year, season) -> [pm25, ...]
    buckets: dict[tuple, list[float]] = defaultdict(list)
    files = sorted(data_dir.glob(f"sc_{city_slug}_[0-9]*.jsonl"))
    for fpath in files:
        print(f"Reading {fpath.name}…")
        for line in fpath.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r["pm25"] > PM25_SEASONAL_MAX:  # drop stuck-high faulty sensors
                continue
            nid = nearest_neighbourhood(r["lat"], r["lon"], neighbourhoods)
            if nid is None:
                continue
            buckets[(nid, r["year"], r["season"])].append(r["pm25"])

    # Replace the whole city's rows (idempotent re-run).
    nbhd_ids = [n.id for n in neighbourhoods]
    if nbhd_ids:
        session.execute(
            delete(NeighbourhoodAir).where(NeighbourhoodAir.neighbourhood_id.in_(nbhd_ids))
        )

    for (nid, year, season), vals in buckets.items():
        pm25 = sum(vals) / len(vals)
        session.add(NeighbourhoodAir(
            neighbourhood_id=nid, year=year, season=season,
            pm25_avg=round(pm25, 2), aqi_avg=float(pm25_to_aqi(pm25)),
            sensor_count=len(vals),
        ))

    session.commit()
    print(f"Wrote {len(buckets)} neighbourhood-season rows "
          f"from {len(files)} year files.")


if __name__ == "__main__":
    import re

    engine = create_engine(DATABASE_URL)
    data_dir = Path(__file__).parent.parent / "data" / "raw" / "air_quality"
    # Aggregate every city that has crawled year files (sc_<city>_<year>.jsonl).
    # Each city's rows are replaced independently, so re-running is safe and a new
    # city's data simply gets picked up without touching the others.
    cities = sorted({
        m.group(1)
        for f in data_dir.glob("sc_*_[0-9]*.jsonl")
        if (m := re.match(r"sc_(.+)_\d{4}$", f.stem))
    })
    with Session(engine) as session:
        for city in cities:
            print(f"\n### {city} ###")
            aggregate(session, data_dir, city)
