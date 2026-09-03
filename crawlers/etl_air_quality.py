#!/usr/bin/env python3
"""Load AQICN air quality JSONL into the DB and map neighbourhoods to stations.

Usage:
    cd backend && python3 ../crawlers/etl_air_quality.py
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from sqlalchemy import create_engine, select, delete
from sqlalchemy.orm import Session

from app.db import DATABASE_URL
from app.models import (AirQualitySnapshot, AirQualityStation, City,
                        Neighbourhood, NeighbourhoodAirStation)

MAX_STATION_DISTANCE_M = 5000  # 5 km radius for neighbourhood→station mapping


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    dφ = math.radians(lat2 - lat1)
    dλ = math.radians(lon2 - lon1)
    a = math.sin(dφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(dλ / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def load_stations_and_snapshots(session: Session, data_dir: Path) -> None:
    """Upsert stations + snapshots from all aqicn_*_<year>.jsonl files."""
    station_cache: dict[tuple, int] = {}  # (uid, city_slug) -> station.id

    city_ids: dict[str, int] = {
        row.slug: row.id for row in session.scalars(select(City)).all()
    }

    for fpath in sorted(data_dir.glob("aqicn_*_[0-9]*.jsonl")):
        print(f"Loading {fpath.name}...")
        rows = [json.loads(l) for l in fpath.read_text().splitlines() if l.strip()]
        for r in rows:
            uid = str(r["uid"])
            city_slug = r["city"]
            cache_key = (uid, city_slug)

            if cache_key not in station_cache:
                existing = session.scalar(
                    select(AirQualityStation).where(
                        AirQualityStation.external_id == uid,
                        AirQualityStation.city_id == city_ids.get(city_slug),
                    )
                )
                if existing:
                    station_cache[cache_key] = existing.id
                else:
                    st = AirQualityStation(
                        name=r["station_name"],
                        source=r.get("source", "official"),
                        lat=r.get("lat"),
                        lon=r.get("lon"),
                        city_id=city_ids.get(city_slug),
                        external_id=uid,
                    )
                    session.add(st)
                    session.flush()
                    station_cache[cache_key] = st.id

            station_id = station_cache[cache_key]
            existing_snap = session.scalar(
                select(AirQualitySnapshot).where(
                    AirQualitySnapshot.station_id == station_id,
                    AirQualitySnapshot.year == r["year"],
                )
            )
            if existing_snap:
                existing_snap.pm25_annual_avg = r.get("pm25_annual_avg")
                existing_snap.aqi_annual_avg = r.get("aqi_annual_avg")
            else:
                session.add(AirQualitySnapshot(
                    station_id=station_id,
                    year=r["year"],
                    pm25_annual_avg=r.get("pm25_annual_avg"),
                    aqi_annual_avg=r.get("aqi_annual_avg"),
                ))

    session.commit()
    print(f"Stations loaded: {len(station_cache)}")


def map_neighbourhoods(session: Session) -> None:
    """For each neighbourhood, find the nearest station within 5 km and write the mapping."""
    session.execute(delete(NeighbourhoodAirStation))

    neighbourhoods = session.scalars(select(Neighbourhood)).all()
    stations = session.scalars(select(AirQualityStation)).all()

    mapped = 0
    for n in neighbourhoods:
        if n.lat is None or n.lon is None:
            continue

        # Official stations first, then citizen sensors
        best: tuple | None = None  # (distance_m, station_id, source)
        for st in stations:
            if st.lat is None or st.lon is None:
                continue
            if st.city_id is not None and st.city_id != n.city_id:
                continue
            dist = haversine_m(float(n.lat), float(n.lon), float(st.lat), float(st.lon))
            if dist > MAX_STATION_DISTANCE_M:
                continue
            if best is None or dist < best[0] or (dist == best[0] and st.source == "official"):
                best = (dist, st.id, st.source)

        if best:
            session.add(NeighbourhoodAirStation(
                neighbourhood_id=n.id,
                station_id=best[1],
                distance_m=int(best[0]),
            ))
            mapped += 1

    session.commit()
    print(f"Neighbourhood→station mappings: {mapped} / {len(neighbourhoods)}")


if __name__ == "__main__":
    engine = create_engine(DATABASE_URL)
    data_dir = Path(__file__).parent.parent / "data" / "raw" / "air_quality"
    with Session(engine) as session:
        load_stations_and_snapshots(session, data_dir)
        map_neighbourhoods(session)
