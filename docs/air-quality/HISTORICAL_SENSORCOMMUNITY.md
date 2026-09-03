# Historical Air Quality from Sensor.Community (Map Year Slider)

> **Status:** Full multi-year, multi-city pull complete (run 2026-06-18). `neighbourhood_air`
> holds all four cities — Sofia (94 nbhds, 2017–2026, 279 sensors), Plovdiv (18/42, 2018–26,
> 32 sensors), Varna (12/71, 14 sensors), Burgas (2/29, just 2 sensors — citizen coverage is
> sparse on the coast). Crawler + ETL are now city-parameterised; both re-runnable to refresh.
> **Goal:** Populate the map's AQI/PM2.5 metrics with **year-over-year** citizen-sensor data so the year slider shows how Sofia's air changed over time.

## Why Sensor.Community (not AQICN)

AQICN's free API has **no history** — only a live reading + a ~1-week forecast. Sensor.Community (the citizen "hobby sensor" network, formerly luftdaten) has an **open archive going back to 2015** and **~280 PM sensors in Sofia right now** (vs ~8 official AQICN stations). That density + depth is the only realistic source for the trend view.

It feeds the **existing pipeline unchanged**: this crawler emits the same JSONL schema the ETL already reads, with `source="citizen"`. So:

```
fetch_air_quality_sensorcommunity.py  →  data/raw/air_quality/sc_sofia_<year>.jsonl
        →  etl_air_quality.py  →  DB (air_quality_*)  →  /api/map `air` key  →  map year slider
```

## Verified archive structure (so you understand the crawler)

The crawler handles the archive's two layouts automatically:

| Data age | Path | Format |
|---|---|---|
| Completed years (2015–2024) | `archive.sensor.community/{YYYY}/{date}/{date}_sds011_sensor_{id}.csv.gz` | gzipped CSV |
| Current rolling year | `archive.sensor.community/{date}/{date}_sds011_sensor_{id}.csv` | plain CSV |

It tries the gzipped historical path first, falls back to the plain root path — so it works across the retention boundary with no config.

**Why not the monthly bulk zips?** `csv_per_month/{YYYY-MM}/{YYYY-MM}_sds011.zip` exists but each is **~3.9 GB** (all global sensors). 12 months × 11 years ≈ **490 GB** — impractical. The crawler instead fetches only Sofia roster sensors, sampled.

## Sampling strategy: two seasonal snapshots, aggregated per neighbourhood

Two design choices keep this tiny and meaningful (decided 2026-06-17):

1. **Two seasons, not 12 months.** Air is strongly seasonal — Sofia's winter PM2.5 is 3–5× summer (heating season). The crawler samples only **January (winter)** and **July (summer)**, a few days each. That's ~12× less downloading than a full-year sample, and the winter value is the differentiating, health-relevant one.
2. **Aggregate per neighbourhood, not per sensor.** The ETL averages *all* sensors that fall inside each neighbourhood (within 2 km of its centre) into one value per (neighbourhood, year, season). Averaging many cheap SDS011 sensors cancels their noise, and the DB stores only **~62 × years × 2 ≈ 1,400 rows** total.

Validated end-to-end (60-sensor subset, 2023–2024): real winter>summer split per neighbourhood (e.g. Орландовци 14.1 winter / 1.4 summer µg/m³). The full ~280-sensor crawl raises the sensor count per neighbourhood and smooths the few single-sensor outliers.

## How to run the full pull

```bash
cd /Users/gabe/Dev/bg-realestate-intel

# 1. Full crawl. With no --city it does ALL cities in CITY_BOUNDS (sofia, varna,
#    plovdiv, burgas); pass --city <slug> for one. Discovers each city's current
#    SDS011 roster (cached to sc_<city>_sensors.json), then pulls each sensor's
#    seasonal days per year. Re-runnable (each year file is overwritten).
backend/.venv/bin/python crawlers/fetch_air_quality_sensorcommunity.py --years 2015-2026 --days-per-season 5
# one city only:
backend/.venv/bin/python crawlers/fetch_air_quality_sensorcommunity.py --city plovdiv --years 2017-2026 --days-per-season 5

# 2. Aggregate sensors → per-neighbourhood seasonal averages (writes neighbourhood_air).
set -a; source .env; set +a
cd backend && .venv/bin/python ../crawlers/etl_neighbourhood_air.py && cd ..

# 3. Drop the in-memory /map cache so the API serves the new air data.
curl -s -X POST -H "x-admin-token: $ADMIN_TOKEN" http://localhost:8000/api/admin/refresh-cache

# 4. View: open /c/sofia, pick AQI or PM2.5, toggle Winter/Summer, drag the year slider.
```

> ✅ The full crawl + ETL has been run (2026-06-18): `data/raw/air_quality/` holds
> `sc_sofia_2015…2026.jsonl` (2,548 sensor-seasons) and the live DB's `neighbourhood_air`
> holds the full aggregate. Re-running steps 1–2 overwrites the year files and replaces
> all Sofia rows, so it's safe to refresh anytime.

## Tuning

| Flag | Default | Notes |
|---|---|---|
| `--years` | `2015-2026` | range or single year |
| `--days-per-season` | `5` | sample days in Jan and in Jul; higher = smoother, slower |
| `--max-sensors` | `0` (all) | cap for quick test runs |
| `--sleep` | `0.05` | seconds between requests — be polite to the archive |

## Known limitations (be honest about the data)

- **Roster = current sensors.** The crawler uses sensors that exist in Sofia *today*. Sensors that ran 2015–2020 but are now offline are missed, so older years have thinner coverage. Good enough for a trend; not a census.
- **Citizen-sensor quality.** SDS011 sensors are cheap and read high in humidity/fog. Annual averaging smooths most noise; the crawler's per-reading filter drops faults (PM2.5 ≤0.5 or >1000). A second filter in the ETL drops any *sensor-season mean* above `PM25_SEASONAL_MAX` (150 µg/m³) — a stuck-high sensor can pass the per-reading cap yet still poison a neighbourhood average (e.g. Дианабад read ~155–177 before, ~13–25 after). Sofia's worst real heating-season means top out ~80–99, which is preserved. Treat values as indicative, not regulatory-grade.
- **Sampled, not exhaustive.** Annual means come from sampled days, not every reading.
- **Coordinates are current positions** applied to all years (sensors rarely move).
- **Official cross-check:** for a regulatory-grade comparison, the EEA air-quality download service has official Sofia station data back 10+ years — a possible future second source alongside this citizen layer (`source` field already distinguishes `citizen` vs `official`).
```
