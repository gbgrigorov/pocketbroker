# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Sofia (Bulgaria) real estate intelligence platform. **Phase 1 is complete** — all raw data has been collected. Phase 2 will build the FastAPI backend + Vue 3 frontend.

See [HANDOVER.md](HANDOVER.md) for the full Phase 1 summary and Phase 2 build plan. See [RUNBOOK.md](RUNBOOK.md) for crawler commands and ETL sequencing.

---

## Trello API

```bash
set -a; source /Users/gabe/Dev/bg-realestate-intel/.env; set +a
curl -s "https://api.trello.com/1/<endpoint>?key=$TRELLO_API_KEY&token=$TRELLO_TOKEN"
```

Key board IDs (board "Gaby - Week Plans"):
- Board: `5e891bb77638443ae70b8781`
- Backlog: `5e891bc85fc3198d8973e6b3`
- To Do: `5e891bd54dd559540d3b28f4`
- In Progress: `6a12aa1b57fcdffc097b5e0b`
- Done: `5e891c2a0a2c177716d9c8df`

---

## Running the Crawlers

All crawlers are standalone Python 3 scripts. Dependencies: `httpx`, `beautifulsoup4`.

```bash
# Monthly current price snapshot (364 records, one request to imot.bg)
python3 crawlers/imot_prices.py > data/raw/imot_bg/sofia_current_$(date +%Y-%m).jsonl

# Add one year to history (October snapshot)
python3 crawlers/imot_bg_history.py --start-year 2026 --end-year 2026 \
  --output-dir data/raw/imot_bg/sofia_history

# Full historical re-run (31 years, ~35 min)
python3 crawlers/imot_bg_history.py --output-dir data/raw/imot_bg/sofia_history

# Geocoding pipeline (one-time; resume after interruption with --resume)
python3 crawlers/geocode_neighbourhoods.py
python3 crawlers/geocode_neighbourhoods.py --resume
python3 crawlers/verify_coords.py
python3 crawlers/apply_verified_coords.py

# Transport data (re-run when Overpass API is accessible — currently returns 406)
python3 crawlers/fetch_transport.py --output data/raw/transport/sofia_transport.json
```

No build, lint, or test commands exist yet — Phase 2 will add those.

---

## Data Pipeline Architecture

### Phase 1 (Complete): Raw Data Collection

```
imot.bg (current prices)  →  crawlers/imot_prices.py    →  data/raw/imot_bg/sofia_current_YYYY-MM.jsonl
imot.bg (1995–2025 hist)  →  crawlers/imot_bg_history.py →  data/raw/imot_bg/sofia_history/YYYY_october.jsonl
Nominatim OSM             →  crawlers/geocode_neighbourhoods.py → verify_coords.py → apply_verified_coords.py
Overpass API (OSM)        →  crawlers/fetch_transport.py  →  data/raw/transport/sofia_transport.json ⚠️ PARTIAL
```

**What's collected:**
- **9,663 price records** — 364 current (May 2026) + 9,299 historical (1995–2025, October snapshots)
- **62 neighbourhood coordinates** — verified via OSM Nominatim; canonical file is `sofia_neighbourhood_coords.json`
- **8 metro stations** — partial (Overpass API returned HTTP 406 on 2026-05-26)

### Phase 2 (Planned): Backend + Frontend

```
data/raw/ (JSONL files)
    ↓ ETL (to be built)
PostgreSQL (VPS: <VPS_IP>)
    ↓
FastAPI + SQLAlchemy + Alembic + Uvicorn
    ↓ REST API
Vue 3 + Vite + Pinia + Leaflet.js + D3.js v7
    ↓ Nginx (same VPS) or Vercel
Browser
```

---

## Key Data Schemas

### Price Record (JSONL) — Current Snapshot

```json
{
  "source": "imot.bg",
  "city": "sofia",
  "neighborhood": "Лозенец",
  "neighborhood_slug": "lozenets",
  "property_type": "двустаен",
  "price_eur": 180000.0,
  "price_bgn": 352049.98,
  "price_eur_sqm": 3450.0,
  "price_bgn_sqm": 6746.59,
  "overall_avg_eur_sqm": 3200.0,
  "period_date": "2026-05-01",
  "scraped_at": "2026-05-26T08:52:44.932151Z"
}
```

### Price Record (JSONL) — Historical

Identical to above except `neighborhood_slug` is **always `null`** (historical pages have no href links). ETL must resolve slug via Bulgarian name lookup against the current snapshot.

### Neighbourhood Coordinates (JSON object)

```json
{
  "lozenets": { "name": "Лозенец", "lat": 42.6597151, "lon": 23.3250228, "source": "nominatim", "verified": true }
}
```

---

## Database Schema (Designed, Not Yet Deployed)

```sql
CREATE TABLE city (id SERIAL PRIMARY KEY, name TEXT, slug TEXT UNIQUE);
CREATE TABLE neighbourhood (
  id SERIAL PRIMARY KEY, city_id INT REFERENCES city(id),
  name TEXT NOT NULL, slug TEXT UNIQUE, district TEXT,
  lat NUMERIC(9,7), lon NUMERIC(9,7), coord_source TEXT,
  created_at TIMESTAMP DEFAULT now()
);
CREATE TABLE price_snapshot (
  id SERIAL PRIMARY KEY, neighbourhood_id INT REFERENCES neighbourhood(id),
  source TEXT, property_type TEXT,
  price_eur NUMERIC, price_bgn NUMERIC, price_eur_sqm NUMERIC,
  price_bgn_sqm NUMERIC, overall_avg_eur_sqm NUMERIC,
  period_date DATE, scraped_at TIMESTAMP
);
CREATE TABLE metro_station (
  id SERIAL PRIMARY KEY, name TEXT, line TEXT,
  lat NUMERIC(9,7), lon NUMERIC(9,7), sequence INT
);
CREATE TABLE neighbourhood_metro (
  neighbourhood_id INT REFERENCES neighbourhood(id),
  station_id INT REFERENCES metro_station(id),
  distance_m INT, PRIMARY KEY (neighbourhood_id, station_id)
);
CREATE TABLE neighbourhood_adjacency (
  from_id INT REFERENCES neighbourhood(id),
  to_id INT REFERENCES neighbourhood(id),
  direction TEXT CHECK (direction IN ('N','S','E','W','NE','NW','SE','SW')),
  PRIMARY KEY (from_id, to_id)
);
```

---

## Planned API Endpoints

```
GET /api/neighbourhoods                  → List all 62 with coords
GET /api/neighbourhoods/{slug}           → Single neighbourhood detail
GET /api/neighbourhoods/{slug}/prices    → Price history (for chart)
GET /api/map?metric=...&year=...         → All neighbourhoods + metric values
GET /api/metro/lines                     → Metro station sequences
```

---

## Design System (Neo-Memphis)

Design mockups are in [design/](design/). The UI uses a strict Neo-Memphis visual language:

| Token | Value |
|-------|-------|
| Background | `#F5EED9` (cream) |
| Surface/cards | `#FFFFFF` |
| Border/text | `#0D0D0D` (2px thick black strokes) |
| Primary accent | `#FF3366` (hot pink — CTAs, active bubbles) |
| Secondary accent | `#00D4CC` (teal) |
| Metro M1 | `#2B6BFF` (electric blue) |
| Stat tile accent | `#FF6B47` (coral) |
| Neutral | `#C4C4C4` |
| Display font | Barlow Condensed ExtraBold, uppercase |
| Headings | Space Grotesk Bold |
| Numbers | Barlow Condensed Bold |
| Mono | JetBrains Mono, 13px |

**Rules:** flat fills only (no gradients), hard geometric shadows (no soft shadows), thick 2px black outlines on all cards.

---

## Known Issues & Outstanding Tasks

| Issue | Priority | Notes |
|-------|----------|-------|
| Transport data incomplete (Overpass 406) | High | Re-run `fetch_transport.py` when Overpass accessible |
| 6 neighbourhood coords outside Sofia bbox | Medium | Люлин 1, Люлин 7, Яворов, Лагера, Банишора, Дружба 1 |
| `neighborhood_slug` null in all historical records | ETL blocker | Resolve via name→slug map built from current snapshot |
| Neighbourhood adjacency table empty | Manual | ~50 pairs with N/S/E/W directions need manual curation |
| Intermediate files in `data/raw/transport/` | Cleanup | `*.tmp.json`, `*_corrected.json`, `sofia_coords_verified.json` safe to delete |
| `deploy/ENTITY_PUSH.md` is destructive | Deprecated | Full-mirrors entity tables; would erase API-written findings. Use `scripts/pb.py` — see `deploy/SYNC_API.md` |

---

## Crawler Implementation Notes

- **imot.bg encoding:** Windows-1251 — crawlers use `errors='replace'`
- **Nominatim rate limit:** 1 req/sec enforced in all geocoding scripts
- **Numbered sub-districts** (Люлин 1–10, Надежда 1–4, Младост 1–4): query Nominatim with `"ж.к. <name> София"` format
- **Currency conversion:** Fixed rate 1 EUR = 1.95583 BGN (Bulgaria pegged to EUR)
- **Geocoder resume:** `geocode_neighbourhoods.py` writes a `.tmp` file after each request; use `--resume` to continue interrupted runs
- **Transport proximity radii:** Metro 1200m, Tram 600m, Bus 500m (used in `fetch_transport.py`)
