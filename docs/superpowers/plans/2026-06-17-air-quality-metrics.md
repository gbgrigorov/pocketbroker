# Air Quality Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add AQI and PM2.5 as two new switchable bubble-map metrics sourced from AQICN (official stations) and Sensor.Community (citizen fill), visualised with the existing year-slider pattern.

**Architecture:** A Python crawler fetches station data from AQICN API and stores annual averages as JSONL; an ETL script loads them into three new DB tables; the `/api/map` endpoint is extended to include an `air` key per neighbourhood; two new metric definitions in `metrics.js` enable the frontend slider/metric-switch without any structural frontend changes.

**Tech Stack:** Python 3 + httpx (crawler), SQLAlchemy mapped columns (models), Alembic (migration), FastAPI (routes), Vue 3 + D3 (frontend — existing, extended only).

## Global Constraints

- All `.env` reads in crawlers must use `os.environ.get(...)` — never hard-code tokens
- `AQICN_TOKEN` must be present in `.env` before the crawler can run
- Annual averages are the unit of storage — one row per station per year
- Neighbourhood → station mapping: official station within 5 km first; citizen sensor within 5 km as fallback; `null` if nothing within 5 km
- All new model columns follow the existing `Mapped[Optional[...]]` nullable pattern
- Alembic revision IDs follow the existing hex-slug convention (see `f1a2b3c4d5e6_entity_signal_hidden_flag.py`)
- i18n keys must be added to both `frontend/src/i18n/messages/en.js` AND `bg.js` — key parity enforced
- WHO PM2.5 colour thresholds: ≤12 green, 12–35 yellow, 35–55 orange, 55+ red
- AQI colour thresholds: ≤50 green, 51–100 yellow, 101–150 orange, 150+ red

---

## File Map

| Path | Action | Responsibility |
|------|--------|---------------|
| `backend/app/models.py` | Modify | Add `AirQualityStation`, `AirQualitySnapshot`, `NeighbourhoodAirStation` |
| `backend/alembic/versions/a1b2c3d4e5f6_air_quality_tables.py` | Create | Schema migration for the 3 new tables |
| `crawlers/fetch_air_quality.py` | Create | Fetch AQICN stations + annual averages; write JSONL |
| `crawlers/etl_air_quality.py` | Create | Load JSONL into DB; compute neighbourhood→station mapping |
| `backend/app/routes.py` | Modify | Extend `/map` to include `air` key per neighbourhood |
| `frontend/src/lib/metrics.js` | Modify | Add `aqi` and `pm25` metric definitions + update `METRIC_ORDER` |
| `frontend/src/i18n/messages/en.js` | Modify | Add EN labels for `metrics.aqi` and `metrics.pm25` |
| `frontend/src/i18n/messages/bg.js` | Modify | Add BG labels for `metrics.aqi` and `metrics.pm25` |

---

## Task 1: DB Models

**Files:**
- Modify: `backend/app/models.py`

**Interfaces:**
- Produces:
  - `AirQualityStation` — columns: `id`, `name`, `source` (`'official'|'citizen'`), `lat`, `lon`, `city_id` (FK→city), `external_id` (e.g. AQICN station UID)
  - `AirQualitySnapshot` — columns: `id`, `station_id` (FK→air_quality_station), `year` (int), `pm25_annual_avg` (nullable float), `aqi_annual_avg` (nullable float)
  - `NeighbourhoodAirStation` — composite PK `(neighbourhood_id, station_id)`, plus `distance_m` (int)

- [ ] **Add models** — append to `backend/app/models.py` after the `MinWage` class (before the Phase 3 comment):

```python
# --- Air quality: station registry + annual averages + neighbourhood mapping ---


class AirQualityStation(Base):
    """An air quality monitoring station (official government or citizen sensor)."""

    __tablename__ = "air_quality_station"

    id: Mapped[int] = mapped_column(primary_key=True)
    city_id: Mapped[Optional[int]] = mapped_column(ForeignKey("city.id"), nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)  # 'official' | 'citizen'
    lat: Mapped[Optional[float]] = mapped_column(Numeric(9, 7), nullable=True)
    lon: Mapped[Optional[float]] = mapped_column(Numeric(9, 7), nullable=True)
    external_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    snapshots: Mapped[List["AirQualitySnapshot"]] = relationship(
        back_populates="station", cascade="all, delete-orphan"
    )


class AirQualitySnapshot(Base):
    """Annual average air quality readings for one station."""

    __tablename__ = "air_quality_snapshot"
    __table_args__ = (
        UniqueConstraint("station_id", "year", name="uq_aq_station_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("air_quality_station.id"))
    year: Mapped[int] = mapped_column(nullable=False)
    pm25_annual_avg: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    aqi_annual_avg: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)

    station: Mapped["AirQualityStation"] = relationship(back_populates="snapshots")


class NeighbourhoodAirStation(Base):
    """Maps each neighbourhood to its nearest air quality station (pre-computed)."""

    __tablename__ = "neighbourhood_air_station"

    neighbourhood_id: Mapped[int] = mapped_column(
        ForeignKey("neighbourhood.id"), primary_key=True
    )
    station_id: Mapped[int] = mapped_column(
        ForeignKey("air_quality_station.id"), primary_key=True
    )
    distance_m: Mapped[Optional[int]] = mapped_column(nullable=True)
```

- [ ] **Verify** — `python3 -c "from backend.app.models import AirQualityStation, AirQualitySnapshot, NeighbourhoodAirStation; print('ok')"` from the repo root (or equivalent import check)

- [ ] **Commit**

```bash
git add backend/app/models.py
git commit -m "feat(air-quality): add AirQualityStation, AirQualitySnapshot, NeighbourhoodAirStation models"
```

---

## Task 2: Alembic Migration

**Files:**
- Create: `backend/alembic/versions/a1b2c3d4e5f6_air_quality_tables.py`

**Interfaces:**
- Consumes: models from Task 1 (uses `op.create_table` matching those columns)
- Produces: three new tables in the DB

- [ ] **Create migration file** at `backend/alembic/versions/a1b2c3d4e5f6_air_quality_tables.py`:

```python
"""air quality tables

Adds air_quality_station, air_quality_snapshot, neighbourhood_air_station
for the AQI / PM2.5 bubble-map metrics.

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-06-17 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'air_quality_station',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('city_id', sa.Integer(), sa.ForeignKey('city.id'), nullable=True),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('lat', sa.Numeric(9, 7), nullable=True),
        sa.Column('lon', sa.Numeric(9, 7), nullable=True),
        sa.Column('external_id', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'air_quality_snapshot',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('station_id', sa.Integer(), sa.ForeignKey('air_quality_station.id'), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('pm25_annual_avg', sa.Numeric(), nullable=True),
        sa.Column('aqi_annual_avg', sa.Numeric(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('station_id', 'year', name='uq_aq_station_year'),
    )
    op.create_table(
        'neighbourhood_air_station',
        sa.Column('neighbourhood_id', sa.Integer(), sa.ForeignKey('neighbourhood.id'), nullable=False),
        sa.Column('station_id', sa.Integer(), sa.ForeignKey('air_quality_station.id'), nullable=False),
        sa.Column('distance_m', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('neighbourhood_id', 'station_id'),
    )


def downgrade() -> None:
    op.drop_table('neighbourhood_air_station')
    op.drop_table('air_quality_snapshot')
    op.drop_table('air_quality_station')
```

- [ ] **Run migration** (run from `backend/` directory):

```bash
cd backend && alembic upgrade head
```

Expected output: `Running upgrade f1a2b3c4d5e6 -> a1b2c3d4e5f6, air quality tables`

- [ ] **Commit**

```bash
git add backend/alembic/versions/a1b2c3d4e5f6_air_quality_tables.py
git commit -m "feat(air-quality): alembic migration — add air quality tables"
```

---

## Task 3: AQICN Crawler

**Files:**
- Create: `crawlers/fetch_air_quality.py`
- Output: `data/raw/air_quality/aqicn_<city>_stations.jsonl` (station registry) and `data/raw/air_quality/aqicn_<city>_<year>.jsonl` (annual readings)

**Interfaces:**
- Consumes: `AQICN_TOKEN` from env; city bounding boxes defined inline
- Produces: JSONL records with keys: `station_id`, `station_name`, `source`, `lat`, `lon`, `city`, `year`, `pm25_annual_avg`, `aqi_annual_avg`

**AQICN API notes:**
- Station list: `https://api.waqi.info/v2/map/bounds?latlng={lat1},{lon1},{lat2},{lon2}&networks=all&token={token}`
- Station feed (current + history): `https://api.waqi.info/feed/@{uid}/?token={token}` — returns `data.forecast.daily.pm25` (array of `{avg, day}`) and real-time `data.aqi`
- For annual averages: filter `forecast.daily.pm25` by year and average the `avg` values; AQI is computed from PM2.5 using the EPA breakpoints (see formula in step below)
- Historical data depth varies per station — crawl all years available in the forecast window; for deeper history use `https://api.waqi.info/api/feed/@{uid}/obs.en.json?token={token}` if available

- [ ] **Create `crawlers/fetch_air_quality.py`**:

```python
#!/usr/bin/env python3
"""Fetch Sofia (and other BG cities) air quality data from AQICN.

Usage:
    python3 crawlers/fetch_air_quality.py --city sofia
    python3 crawlers/fetch_air_quality.py  # all cities

Output: data/raw/air_quality/aqicn_{city}_{year}.jsonl
        data/raw/air_quality/aqicn_{city}_stations.jsonl
"""
import argparse
import json
import math
import os
import time
from datetime import date
from pathlib import Path

import httpx

TOKEN = os.environ.get("AQICN_TOKEN", "")

# Bounding boxes: (lat_min, lon_min, lat_max, lon_max)
CITY_BOUNDS = {
    "sofia":   (42.60, 23.20, 42.78, 23.45),
    "varna":   (43.16, 27.83, 43.24, 27.98),
    "plovdiv": (42.11, 24.70, 42.17, 24.80),
    "burgas":  (42.47, 27.44, 42.52, 27.52),
}


def pm25_to_aqi(pm25: float) -> int:
    """EPA linear interpolation from PM2.5 (µg/m³) to AQI (0–500)."""
    breakpoints = [
        (0.0,   12.0,    0,  50),
        (12.1,  35.4,   51, 100),
        (35.5,  55.4,  101, 150),
        (55.5, 150.4,  151, 200),
        (150.5, 250.4, 201, 300),
        (250.5, 350.4, 301, 400),
        (350.5, 500.4, 401, 500),
    ]
    for c_lo, c_hi, i_lo, i_hi in breakpoints:
        if c_lo <= pm25 <= c_hi:
            return round(i_lo + (pm25 - c_lo) / (c_hi - c_lo) * (i_hi - i_lo))
    return 500


def fetch_stations(city: str, bounds: tuple) -> list[dict]:
    lat1, lon1, lat2, lon2 = bounds
    url = (
        f"https://api.waqi.info/v2/map/bounds"
        f"?latlng={lat1},{lon1},{lat2},{lon2}&networks=all&token={TOKEN}"
    )
    r = httpx.get(url, timeout=20)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "ok":
        print(f"  WARN: {city} bounds query returned status={data.get('status')}")
        return []
    stations = []
    for s in data.get("data", []):
        uid = s.get("uid")
        if uid is None:
            continue
        stations.append({
            "uid": uid,
            "name": s.get("station", {}).get("name", ""),
            "lat": s.get("lat"),
            "lon": s.get("lon"),
        })
    print(f"  {city}: found {len(stations)} stations in bounds")
    return stations


def fetch_station_history(uid: int) -> dict:
    """Returns {year: {pm25: avg, aqi: avg}} from station feed."""
    url = f"https://api.waqi.info/feed/@{uid}/?token={TOKEN}"
    r = httpx.get(url, timeout=20)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "ok":
        return {}

    forecast = data.get("data", {}).get("forecast", {}).get("daily", {})
    pm25_days = forecast.get("pm25", [])

    by_year: dict[int, list[float]] = {}
    for entry in pm25_days:
        try:
            d = date.fromisoformat(entry["day"])
            avg = float(entry["avg"])
            by_year.setdefault(d.year, []).append(avg)
        except (KeyError, ValueError):
            continue

    result = {}
    for year, vals in by_year.items():
        pm25_avg = sum(vals) / len(vals)
        result[year] = {
            "pm25": round(pm25_avg, 2),
            "aqi": pm25_to_aqi(pm25_avg),
        }
    return result


def run(cities: list[str]) -> None:
    if not TOKEN:
        raise SystemExit("AQICN_TOKEN not set in environment. Add it to .env and re-run.")

    out_dir = Path("data/raw/air_quality")
    out_dir.mkdir(parents=True, exist_ok=True)

    for city in cities:
        bounds = CITY_BOUNDS[city]
        print(f"\n=== {city} ===")
        stations = fetch_stations(city, bounds)
        time.sleep(1)

        station_file = out_dir / f"aqicn_{city}_stations.jsonl"
        reading_files: dict[int, list] = {}

        for s in stations:
            uid = s["uid"]
            rec = {"uid": uid, "name": s["name"], "lat": s["lat"], "lon": s["lon"],
                   "city": city, "source": "official"}
            with station_file.open("a") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

            print(f"  Fetching uid={uid} ({s['name']})...")
            history = fetch_station_history(uid)
            for year, vals in history.items():
                reading_files.setdefault(year, []).append({
                    "uid": uid, "station_name": s["name"],
                    "lat": s["lat"], "lon": s["lon"],
                    "city": city, "source": "official",
                    "year": year,
                    "pm25_annual_avg": vals["pm25"],
                    "aqi_annual_avg": float(vals["aqi"]),
                })
            time.sleep(1)

        for year, rows in reading_files.items():
            year_file = out_dir / f"aqicn_{city}_{year}.jsonl"
            with year_file.open("w") as f:
                for row in rows:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"  Wrote {len(rows)} rows → {year_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", choices=list(CITY_BOUNDS), help="Single city (default: all)")
    args = parser.parse_args()
    cities = [args.city] if args.city else list(CITY_BOUNDS)
    run(cities)
```

- [ ] **Verify `.env` has AQICN_TOKEN** — `grep AQICN_TOKEN .env` (add the token if missing; get one free at https://aqicn.org/data-platform/token/)

- [ ] **Run a smoke test for Sofia only**:

```bash
set -a; source .env; set +a
python3 crawlers/fetch_air_quality.py --city sofia
```

Expected: creates `data/raw/air_quality/aqicn_sofia_stations.jsonl` and at least one `aqicn_sofia_<year>.jsonl`. Check how many years are available — this tells us historical depth.

- [ ] **Commit**

```bash
git add crawlers/fetch_air_quality.py
git commit -m "feat(air-quality): AQICN crawler — fetch stations + annual PM2.5/AQI averages"
```

---

## Task 4: ETL — Load into DB & Map Neighbourhoods

**Files:**
- Create: `crawlers/etl_air_quality.py`

**Interfaces:**
- Consumes: `data/raw/air_quality/aqicn_*.jsonl` (from Task 3); DB tables from Task 2
- Produces: populated `air_quality_station`, `air_quality_snapshot`, `neighbourhood_air_station` tables

- [ ] **Create `crawlers/etl_air_quality.py`**:

```python
#!/usr/bin/env python3
"""Load AQICN air quality JSONL into the DB and map neighbourhoods to stations.

Usage:
    cd backend && python3 ../crawlers/etl_air_quality.py
"""
import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from sqlalchemy import create_engine, select, delete
from sqlalchemy.orm import Session

from app.models import (AirQualitySnapshot, AirQualityStation, City,
                        Neighbourhood, NeighbourhoodAirStation)

DB_URL = os.environ.get("DATABASE_URL", "sqlite:///test.db")
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
    engine = create_engine(DB_URL)
    data_dir = Path(__file__).parent.parent / "data" / "raw" / "air_quality"
    with Session(engine) as session:
        load_stations_and_snapshots(session, data_dir)
        map_neighbourhoods(session)
```

- [ ] **Run the ETL**:

```bash
set -a; source .env; set +a
cd backend && python3 ../crawlers/etl_air_quality.py
```

Expected: rows printed, no exceptions. Check with:

```bash
cd backend && python3 -c "
from sqlalchemy import create_engine, text
import os
e = create_engine(os.environ['DATABASE_URL'])
with e.connect() as c:
    print('stations:', c.execute(text('SELECT count(*) FROM air_quality_station')).scalar())
    print('snapshots:', c.execute(text('SELECT count(*) FROM air_quality_snapshot')).scalar())
    print('mappings:', c.execute(text('SELECT count(*) FROM neighbourhood_air_station')).scalar())
"
```

Expected: stations ≥ 1, snapshots ≥ 1, mappings ≥ 1

- [ ] **Commit**

```bash
git add crawlers/etl_air_quality.py
git commit -m "feat(air-quality): ETL — load stations/snapshots, map neighbourhoods to nearest station"
```

---

## Task 5: Extend `/api/map` Endpoint

**Files:**
- Modify: `backend/app/routes.py`

**Interfaces:**
- Consumes: `NeighbourhoodAirStation`, `AirQualityStation`, `AirQualitySnapshot` from Task 1
- Produces: each feature in `/api/map` response gains an `air` key:
  ```json
  "air": {
    "2023": { "pm25": 14.2, "aqi": 52, "source": "official", "distance_m": 1200 },
    "2022": { "pm25": 16.1, "aqi": 61, "source": "official", "distance_m": 1200 }
  }
  ```
  `null` is used as the `air` value when no station is within 5 km.

- [ ] **Add import** — in `backend/app/routes.py`, extend the `from app.models import (...)` line to include the three new models:

```python
from app.models import (AirQualitySnapshot, AirQualityStation, Builder, City, CrawlRun,
                        Entity, EntityEdge, EntitySignal, GoldPrice, MinWage,
                        Neighbourhood, NeighbourhoodAirStation, NewBuilding,
                        NewBuildingSource, PriceSnapshot, ResearchRequest)
```

- [ ] **Add helper function** — insert after `_overall_by_year` (before the cache section):

```python
def _air_by_year(session, neighbourhood_id: int) -> Optional[dict]:
    """Air quality readings keyed by year for one neighbourhood, or None if unmapped."""
    mapping = session.scalar(
        select(NeighbourhoodAirStation)
        .where(NeighbourhoodAirStation.neighbourhood_id == neighbourhood_id)
    )
    if mapping is None:
        return None

    snapshots = session.scalars(
        select(AirQualitySnapshot)
        .join(AirQualityStation)
        .where(AirQualitySnapshot.station_id == mapping.station_id)
    ).all()

    source = session.scalar(
        select(AirQualityStation.source)
        .where(AirQualityStation.id == mapping.station_id)
    )

    return {
        str(snap.year): {
            "pm25": _f(snap.pm25_annual_avg),
            "aqi": _f(snap.aqi_annual_avg),
            "source": source,
            "distance_m": mapping.distance_m,
        }
        for snap in snapshots
    } or None
```

- [ ] **Extend `get_map`** — in the `get_map` function, change the `features.append(...)` block to include the `air` key:

```python
    features = []
    for n in session.scalars(stmt).all():
        sale_by_year, sale_latest = _overall_by_year(n, "sale")
        rent_by_year, rent_latest = _overall_by_year(n, "rent")
        by_year = {
            y: {"sale": sale_by_year.get(y), "rent": rent_by_year.get(y)}
            for y in (sale_by_year.keys() | rent_by_year.keys())
        }
        features.append({
            "slug": n.slug, "name": n.name,
            "lat": _f(n.lat), "lon": _f(n.lon),
            "latest": {"sale": sale_latest, "rent": rent_latest},
            "by_year": by_year,
            "air": _air_by_year(session, n.id),
        })
```

- [ ] **Verify** — start the backend and hit the endpoint:

```bash
cd backend && uvicorn app.main:app --reload &
sleep 2
curl -s "http://localhost:8000/api/map?city=sofia" | python3 -c "
import json, sys
data = json.load(sys.stdin)
# Find first neighbourhood with non-null air
for f in data:
    if f.get('air'):
        print(json.dumps({'slug': f['slug'], 'air': f['air']}, indent=2))
        break
else:
    print('No neighbourhood has air quality data yet')
"
```

Expected: at least one neighbourhood with `air` containing year-keyed pm25/aqi values.

- [ ] **Kill dev server** — `pkill -f "uvicorn app.main"` (or Ctrl-C if foregrounded)

- [ ] **Commit**

```bash
git add backend/app/routes.py
git commit -m "feat(air-quality): extend /api/map to include per-neighbourhood air quality by year"
```

---

## Task 6: Frontend Metrics + i18n

**Files:**
- Modify: `frontend/src/lib/metrics.js`
- Modify: `frontend/src/i18n/messages/en.js`
- Modify: `frontend/src/i18n/messages/bg.js`

**Interfaces:**
- Consumes: `f.air` on each map feature — structure `{ [year]: { pm25, aqi, source, distance_m } }`; the active year is resolved by the caller (appStore selects `f.air[activeYear]` before passing `f` to metric functions)
- The metric functions receive a feature `f` where `f.pm25` and `f.aqi` are the year-resolved scalar values (same pattern as `f.sale_eur_sqm` for price)

**Note on data flow:** The appStore currently builds a resolved feature object per year from `by_year`. We need to also merge the active year's air values into `f`. Check `frontend/src/stores/appStore.js` for how `activeYear` is applied — the resolved feature for a given year should include `pm25` and `aqi` top-level keys extracted from `f.air[activeYear]`.

- [ ] **Extend `featuresForYear` getter in `frontend/src/stores/appStore.js`** — the getter currently returns `{ slug, name, lat, lon, value, sale_eur_sqm, rent_eur_sqm }`. Extend it to also resolve air quality values for the active year. Replace the `featuresForYear` getter body:

```js
    featuresForYear() {
      const key = this.year == null ? null : String(this.year)
      return this.rawFeatures.map((f) => {
        const cell = key == null ? f.latest : f.by_year?.[key]
        const sale = cell?.sale ?? null
        const rent = cell?.rent ?? null
        // For "Latest" view (key==null) pick the max available air year
        let airCell = null
        if (f.air) {
          const airKey = key != null
            ? key
            : String(Math.max(...Object.keys(f.air).map(Number)))
          airCell = f.air[airKey] ?? null
        }
        return {
          slug: f.slug, name: f.name, lat: f.lat, lon: f.lon,
          value: sale, sale_eur_sqm: sale, rent_eur_sqm: rent,
          pm25: airCell?.pm25 ?? null,
          aqi: airCell?.aqi ?? null,
          air_source: airCell?.source ?? null,
        }
      })
    },
```

- [ ] **Add metric definitions to `frontend/src/lib/metrics.js`** — replace the `METRIC_ORDER` export and add after the `ptr` definition:

```js
  aqi: {
    key: 'aqi',
    labelKey: 'metrics.aqi.label',
    size: (f) => f.aqi,  // bigger = worse air quality
    valueText: (f) => (f.aqi != null ? 'AQI ' + Math.round(f.aqi) : '—'),
    color: (f) => {
      const v = f.aqi
      if (v == null) return 'var(--neutral)'
      if (v <= 50)  return '#22c55e'   // green — good
      if (v <= 100) return '#eab308'   // yellow — moderate
      if (v <= 150) return '#f97316'   // orange — unhealthy for sensitive groups
      return '#ef4444'                 // red — unhealthy
    },
    legendKey: 'metrics.aqi.legend',
    rankLabelKey: 'metrics.aqi.rankLabel',
    rankValue: (f) => f.aqi,
    rankDir: 'asc',  // lower AQI (cleaner) ranks first
    rankText: (f) => (f.aqi != null ? 'AQI ' + Math.round(f.aqi) : '—'),
  },
  pm25: {
    key: 'pm25',
    labelKey: 'metrics.pm25.label',
    size: (f) => f.pm25,  // bigger = more PM2.5
    valueText: (f) => (f.pm25 != null ? f.pm25.toFixed(1) + ' µg/m³' : '—'),
    color: (f) => {
      const v = f.pm25
      if (v == null) return 'var(--neutral)'
      if (v <= 12)  return '#22c55e'   // green — WHO annual guideline
      if (v <= 35)  return '#eab308'   // yellow — moderate
      if (v <= 55)  return '#f97316'   // orange — unhealthy
      return '#ef4444'                 // red — very unhealthy
    },
    legendKey: 'metrics.pm25.legend',
    rankLabelKey: 'metrics.pm25.rankLabel',
    rankValue: (f) => f.pm25,
    rankDir: 'asc',  // lower PM2.5 ranks first
    rankText: (f) => (f.pm25 != null ? f.pm25.toFixed(1) + ' µg/m³' : '—'),
  },
```

Also update `METRIC_ORDER`:
```js
export const METRIC_ORDER = ['price', 'ptr', 'aqi', 'pm25']
```

- [ ] **Add i18n keys to `frontend/src/i18n/messages/en.js`** — inside the `metrics:` block, after `ptr`:

```js
    aqi: {
      label: 'Air Quality (AQI)',
      legend: 'Bigger + redder = worse air. AQI ≤50 good, 51–100 moderate, 101–150 unhealthy. Click to dive in.',
      rankLabel: 'Cleanest air (AQI)',
    },
    pm25: {
      label: 'PM2.5 (µg/m³)',
      legend: 'Bigger + redder = more fine particles. WHO guideline ≤12 µg/m³. Click to dive in.',
      rankLabel: 'Cleanest air (PM2.5)',
    },
```

- [ ] **Add i18n keys to `frontend/src/i18n/messages/bg.js`** — inside the `metrics:` block, after `ptr`:

```js
    aqi: {
      label: 'Качество на въздуха (AQI)',
      legend: 'По-голям + по-червен = по-лош въздух. AQI ≤50 добър, 51–100 умерен, 101–150 нездравословен. Кликни за детайли.',
      rankLabel: 'Най-чист въздух (AQI)',
    },
    pm25: {
      label: 'PM2.5 (µg/m³)',
      legend: 'По-голям + по-червен = повече фини частици. СЗО норма ≤12 µg/m³. Кликни за детайли.',
      rankLabel: 'Най-чист въздух (PM2.5)',
    },
```

- [ ] **Start the frontend dev server and verify**:

```bash
cd frontend && npm run dev
```

Open `http://localhost:5173/c/sofia` and:
1. Click metric selector → should now show "Air Quality (AQI)" and "PM2.5 (µg/m³)" options
2. Select AQI → bubbles should appear sized and coloured by AQI
3. Move the year slider → bubbles should update
4. Neighbourhoods without a station should appear greyed (null size = no bubble or minimum size)
5. Sidebar rank list should show cleanest-first ordering

- [ ] **Commit**

```bash
git add frontend/src/lib/metrics.js frontend/src/i18n/messages/en.js frontend/src/i18n/messages/bg.js
git commit -m "feat(air-quality): add AQI + PM2.5 metrics to bubble map with i18n labels"
```

---

## Verification (End-to-End)

1. **Data depth check** — after running the crawler, inspect available years:

```bash
ls data/raw/air_quality/aqicn_sofia_*.jsonl | grep -v stations | sort
```

Note the earliest year — this is how far back the visualization goes.

2. **DB check**

```bash
cd backend && python3 -c "
from sqlalchemy import create_engine, text
import os
e = create_engine(os.environ['DATABASE_URL'])
with e.connect() as c:
    print('stations:', c.execute(text('SELECT count(*) FROM air_quality_station')).scalar())
    print('years covered:', c.execute(text('SELECT min(year), max(year) FROM air_quality_snapshot')).fetchone())
    print('mapped neighbourhoods:', c.execute(text('SELECT count(*) FROM neighbourhood_air_station')).scalar())
    print('unmapped (Sofia):', c.execute(text('''
        SELECT count(*) FROM neighbourhood n
        JOIN city c ON n.city_id=c.id
        LEFT JOIN neighbourhood_air_station nas ON nas.neighbourhood_id=n.id
        WHERE c.slug=\\'sofia\\' AND nas.neighbourhood_id IS NULL
    ''')).scalar())
"
```

3. **API check**

```bash
curl -s "http://localhost:8000/api/map?city=sofia" | python3 -c "
import json, sys
data = json.load(sys.stdin)
air_count = sum(1 for f in data if f.get('air'))
print(f'Neighbourhoods with air data: {air_count}/{len(data)}')
sample = next(f for f in data if f.get('air'))
print(json.dumps({'slug': sample['slug'], 'air': sample['air']}, indent=2))
"
```

4. **Visual check** — on `http://localhost:5173/c/sofia`:
   - AQI metric shows coloured bubbles (green hillside areas like Лозенец, orange/red near Надежда)
   - Year slider changes values
   - PM2.5 metric works independently
   - Bubble tooltip (if present) shows source label (`official` vs `citizen`)

---

## Out of Scope (Follow-up)

**Sensor.Community citizen sensors** — the plan uses AQICN (official stations) only. Sensor.Community would improve spatial coverage in Sofia (hundreds of sensors vs. 6–8), but requires downloading their archive CSVs and deduplicating sensor quality. Add as a separate task once we know how many Sofia neighbourhoods are unmapped after the AQICN ETL runs.

---

## Rollback

```bash
cd backend && alembic downgrade c7d8e9f0a1b2
```

This drops `neighbourhood_air_station`, `air_quality_snapshot`, `air_quality_station` tables. Frontend metrics degrade gracefully (null checks already in place).
