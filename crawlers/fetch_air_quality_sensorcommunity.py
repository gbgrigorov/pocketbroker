#!/usr/bin/env python3
"""Historical air quality for Sofia from the Sensor.Community citizen archive.

Sensor.Community (formerly luftdaten.info) is a citizen-science network of cheap
PM sensors. Sofia has ~287 SDS011 dust sensors *right now* — far denser than the
~8 official AQICN stations — and the open archive at archive.sensor.community has
daily per-sensor CSVs going back years. That makes it the only viable source for
"how did Sofia's air change over the years" (AQICN's free API has no history).

Strategy (volume control):
    Downloading every sensor × every day × every year is millions of files. We
    instead SAMPLE a few days per month per sensor and average those — an annual
    mean from ~24 sample-days is a sound estimate and cuts the pull ~15×. Sensors
    that didn't exist in a given year simply 404 and are skipped, so older years
    naturally have fewer sensors.

Output: data/raw/air_quality/sc_sofia_<year>.jsonl — the SAME schema the existing
ETL (crawlers/etl_air_quality.py) already reads, with source="citizen":
    {uid, station_name, lat, lon, city, source, year, pm25_annual_avg, aqi_annual_avg}

So the pipeline is unchanged downstream:
    this crawler → etl_air_quality.py → DB → /api/map `air` key → map year slider.

Usage:
    # discover current Sofia SDS011 sensors (writes the sensor list), then crawl
    python3 crawlers/fetch_air_quality_sensorcommunity.py --years 2015-2026

    # smaller / faster runs
    python3 crawlers/fetch_air_quality_sensorcommunity.py --years 2024-2025 \
        --sample-days 2 --max-sensors 50
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
from pathlib import Path

import httpx

# Reuse the EPA PM2.5→AQI conversion AND the per-city bounding boxes from the
# AQICN crawler (single source of truth — same boxes feed both air sources).
sys.path.insert(0, str(Path(__file__).parent))
from fetch_air_quality import pm25_to_aqi, CITY_BOUNDS  # noqa: E402

ARCHIVE = "https://archive.sensor.community"
LIVE_JSON = "https://data.sensor.community/static/v2/data.json"
UA = {"User-Agent": "bg-realestate-intel/air-history (contact: research)"}

# Plausibility filter for a single SDS011 PM2.5 reading (µg/m³). Drop sensor
# faults: negatives, zeros, and absurd spikes well past "hazardous".
PM_MIN, PM_MAX = 0.5, 1000.0
# A sensor-season needs at least this many valid readings to be trusted.
MIN_READINGS_PER_SEASON = 50


def discover_sensors(city: str, bounds: tuple, cache: Path) -> list[dict]:
    """Current SDS011 sensors in `city`'s bounding box: [{id, lat, lon}]. Cached.

    Uses the *live* feed to get the sensor roster + coordinates. Sensors rarely
    move, so today's coordinates are applied to all historical years.
    """
    if cache.exists():
        return json.loads(cache.read_text())

    print(f"Fetching live sensor roster from {LIVE_JSON} …")
    r = httpx.get(LIVE_JSON, headers=UA, timeout=120)
    r.raise_for_status()
    lat1, lon1, lat2, lon2 = bounds
    seen: dict[int, dict] = {}
    for rec in r.json():
        sensor = rec.get("sensor", {})
        if sensor.get("sensor_type", {}).get("name") != "SDS011":
            continue
        loc = rec.get("location", {})
        try:
            lat, lon = float(loc["latitude"]), float(loc["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if lat1 <= lat <= lat2 and lon1 <= lon <= lon2:
            sid = sensor.get("id")
            if sid is not None and sid not in seen:
                seen[sid] = {"id": sid, "lat": lat, "lon": lon}

    sensors = list(seen.values())
    cache.write_text(json.dumps(sensors, ensure_ascii=False, indent=2))
    print(f"  {len(sensors)} {city} SDS011 sensors → {cache}")
    return sensors


# Two seasonal snapshots per year capture Sofia's huge heating-season swing:
# January = winter (peak PM, most differentiating); July = summer (clean baseline).
SEASONS = {"winter": 1, "summer": 7}


def season_days(year: int, month: int, n_days: int) -> list[str]:
    """ISO dates to sample within one month, spread across it."""
    if n_days <= 1:
        days = [15]
    else:
        step = max(1, 28 // n_days)
        days = list(range(step, 29, step))[:n_days]
    return [f"{year}-{month:02d}-{d:02d}" for d in days]


def _day_urls(sensor_id: int, date: str) -> list[tuple[str, bool]]:
    """Candidate (url, is_gzip) for a sensor-day, in try order.

    The archive stores completed years gzipped under a year-prefixed path
    (``/{YYYY}/{date}/{date}_sds011_sensor_{id}.csv.gz``) and the current rolling
    year as plain CSV at the root (``/{date}/..._sensor_{id}.csv``). We try the
    gzipped historical path first, then fall back to the root plain CSV, so the
    crawler works across the rolling-retention boundary without hard-coding it.
    """
    year = date[:4]
    return [
        (f"{ARCHIVE}/{year}/{date}/{date}_sds011_sensor_{sensor_id}.csv.gz", True),
        (f"{ARCHIVE}/{date}/{date}_sds011_sensor_{sensor_id}.csv", False),
    ]


def fetch_day_pm25(client: httpx.Client, sensor_id: int, date: str) -> list[float]:
    """Valid PM2.5 (P2) readings for one sensor on one day. [] on 404/empty."""
    text = None
    for url, is_gzip in _day_urls(sensor_id, date):
        try:
            r = client.get(url, headers=UA, timeout=30)
        except httpx.HTTPError:
            continue
        if r.status_code != 200 or not r.content:
            continue
        try:
            text = gzip.decompress(r.content).decode("utf-8", "replace") if is_gzip else r.text
        except (OSError, EOFError):
            continue
        break
    if not text:
        return []

    out: list[float] = []
    lines = text.splitlines()
    for line in lines[1:]:  # skip header
        parts = line.split(";")
        if len(parts) < 10:
            continue
        try:
            p2 = float(parts[9])  # P2 = PM2.5
        except (ValueError, IndexError):
            continue
        if PM_MIN <= p2 <= PM_MAX:
            out.append(p2)
    return out


def crawl(city: str, years: range, sensors: list[dict], days_per_season: int,
          out_dir: Path, sleep_s: float) -> None:
    """Emit per-sensor seasonal PM2.5 rows (winter/summer) → sc_<city>_<year>.jsonl.

    Aggregation to neighbourhood level happens later in the ETL; here we keep one
    row per (sensor, year, season) so the ETL can average all sensors per area.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    with httpx.Client(follow_redirects=True) as client:
        for year in years:
            rows = []
            print(f"\n=== {city} {year} ({len(sensors)} sensors × {len(SEASONS)} "
                  f"seasons × {days_per_season} days) ===")
            for season, month in SEASONS.items():
                days = season_days(year, month, days_per_season)
                kept = 0
                for s in sensors:
                    readings: list[float] = []
                    for date in days:
                        readings.extend(fetch_day_pm25(client, s["id"], date))
                        if sleep_s:
                            time.sleep(sleep_s)
                    if len(readings) < MIN_READINGS_PER_SEASON:
                        continue
                    pm25 = round(sum(readings) / len(readings), 2)
                    rows.append({
                        "uid": s["id"],
                        "lat": s["lat"], "lon": s["lon"],
                        "city": city, "source": "citizen",
                        "year": year, "season": season,
                        "pm25": pm25,
                        "aqi": float(pm25_to_aqi(pm25)),
                    })
                    kept += 1
                print(f"  {season}: {kept}/{len(sensors)} sensors with enough data")

            out_file = out_dir / f"sc_{city}_{year}.jsonl"
            with out_file.open("w") as f:
                for row in rows:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"  Wrote {len(rows)} sensor-seasons → {out_file}")


def parse_years(spec: str) -> range:
    if "-" in spec:
        a, b = spec.split("-")
        return range(int(a), int(b) + 1)
    y = int(spec)
    return range(y, y + 1)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--years", default="2015-2026", help="e.g. 2015-2026 or 2024")
    p.add_argument("--days-per-season", type=int, default=5,
                   help="sample days in Jan and in Jul per sensor (default 5)")
    p.add_argument("--max-sensors", type=int, default=0,
                   help="cap sensor count for a quick run (0 = all)")
    p.add_argument("--sleep", type=float, default=0.05,
                   help="seconds between requests (be polite to the archive)")
    p.add_argument("--city", choices=list(CITY_BOUNDS),
                   help="single city (default: all of " + ", ".join(CITY_BOUNDS) + ")")
    p.add_argument("--out-dir", default="data/raw/air_quality")
    args = p.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    years = parse_years(args.years)
    cities = [args.city] if args.city else list(CITY_BOUNDS)
    for city in cities:
        sensors = discover_sensors(city, CITY_BOUNDS[city], out_dir / f"sc_{city}_sensors.json")
        if args.max_sensors:
            sensors = sensors[: args.max_sensors]
        crawl(city, years, sensors, args.days_per_season, out_dir, args.sleep)
