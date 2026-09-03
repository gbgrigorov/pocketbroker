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
    """EPA linear interpolation from PM2.5 (µg/m³) to AQI (0–500).

    PM2.5 is truncated to 1 decimal place before lookup, per the official EPA
    algorithm. This also closes the gaps between non-contiguous breakpoints
    (e.g. 12.05 → 12.0), which otherwise fall through to the 500 fallback.
    """
    if pm25 <= 0:
        return 0
    pm25 = int(pm25 * 10) / 10.0  # truncate to 1 decimal (EPA method)
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
        station_file.write_text("")  # Truncate once per run to avoid duplicates on re-runs
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
