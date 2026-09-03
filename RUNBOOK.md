# BG Real Estate Intel — RUNBOOK

**Status:** Data preparation phase complete (except transport — see below).
**Next step:** Database setup + ETL pipeline.

---

## What's in this repo

```
bg-realestate-intel/
├── crawlers/
│   ├── imot_prices.py          Current Sofia prices (1 request, all neighbourhoods)
│   ├── imot_bg_history.py      Historical October snapshots 1995–present
│   └── fetch_transport.py      Sofia metro/tram/bus via Overpass API
│
├── data/raw/
│   ├── imot_bg/
│   │   ├── sofia_current_2026-05.jsonl          Current snapshot (May 2026)
│   │   └── sofia_history/
│   │       ├── 1995_october.jsonl  →  2025_october.jsonl   (31 files)
│   └── transport/
│       ├── sofia_transport.json                 ⚠️  PARTIAL — see Transport section
│       └── sofia_neighbourhood_coords.json      Geocoded lat/lon per neighbourhood
```

---

## Data collected

### imot.bg current snapshot
- **File:** `data/raw/imot_bg/sofia_current_2026-05.jsonl`
- **Records:** 364 (141 neighbourhoods × up to 3 property types + overall avg)
- **Re-run:** `python3 crawlers/imot_prices.py > data/raw/imot_bg/sofia_current_YYYY-MM.jsonl`

### imot.bg historical (1995–2025)
- **Files:** `data/raw/imot_bg/sofia_history/YYYY_october.jsonl`
- **Records:** 9,299 total across 31 years
- **Coverage:** All years 1995–2025, October snapshot, closest available date to Oct 15
- **Snapshot dates used:** E.g. 14.10.1995, 17.10.2024, 16.10.2025
- **Property types:** едностаен / двустаен / тристаен (standardised)
- **Fields per record:**
  ```json
  {
    "source": "imot.bg",
    "city": "sofia",
    "year": 2024,
    "snapshot_date": "17.10.2024",
    "period_date": "2024-10-17",
    "neighborhood": "Лозенец",
    "neighborhood_slug": null,
    "property_type": "двустаен",
    "price_eur": 180000.0,
    "price_bgn": 352049.0,
    "price_eur_sqm": 3450.0,
    "price_bgn_sqm": 6747.0,
    "overall_avg_eur_sqm": 3200.0,
    "scraped_at": "2026-05-26T08:47:00Z"
  }
  ```
- **Note:** `neighborhood_slug` is `null` on all historical records — historical pages have no href links. Resolve slug via Bulgarian name lookup in ETL.
- **Re-run single year:** `python3 crawlers/imot_bg_history.py --start-year 2024 --end-year 2024 --output-dir data/raw/imot_bg/sofia_history`
- **Re-run full range:** `python3 crawlers/imot_bg_history.py --output-dir data/raw/imot_bg/sofia_history`

### ⚠️ Transport data — INCOMPLETE
- **Issue:** Overpass API (overpass-api.de) returned HTTP 406 on all endpoints during collection
- **What we have:**
  - `sofia_neighbourhood_coords.json` — geocoded lat/lon for 56/62 neighbourhoods (56 valid, 6 outside Sofia bbox needing review)
  - `sofia_transport.json` — partial metadata + 8 metro stations from Wikidata
- **6 coordinates needing manual review:** `lyulin-1`, `lyulin-7`, `yavorov`, `lagera`, `banishora`, `druzhba-1`
- **To complete:** Run `python3 crawlers/fetch_transport.py --output data/raw/transport/sofia_transport.json` when Overpass is accessible. The crawler geocodes all neighbourhoods (Nominatim) and maps transport routes to them.

---

## ETL — loading into PostgreSQL

### 1. Name → slug resolution

> ⚠️ **Corrected 2026-05-29.** The exact-name match below is BROKEN — it resolves
> only ~137/339 historical names because history is ALL-CAPS (`БАНИШОРА`) and
> sometimes a different string (`БЕЛИ БРЕЗИ` vs current `Белите брези`). The working
> implementation is `backend/etl/neighbourhoods.py` (`NameResolver`): casefold + trim,
> joined on the canonical registry, with an alias map for divergent strings. The ETL
> (`backend/etl/load.py`) loads only the 62 mappable neighbourhoods and reports every
> skipped row — nothing is dropped silently. Build the registry with
> `cd backend && .venv/bin/python -m etl.build_registry`.

Historical records have `neighborhood_slug: null`. The *intended* (but insufficient) approach was:

```python
# NOTE: exact match is insufficient — see warning above. Use NameResolver instead.
import json
slug_map = {}
for line in open("data/raw/imot_bg/sofia_current_2026-05.jsonl"):
    r = json.loads(line)
    slug_map[r["neighborhood"]] = r["neighborhood_slug"]
```

### 2. Recommended DB schema

```sql
-- 4 tables for MVP
CREATE TABLE city (id SERIAL PRIMARY KEY, name TEXT NOT NULL, slug TEXT UNIQUE);
CREATE TABLE neighbourhood (
  id SERIAL PRIMARY KEY,
  city_id INT REFERENCES city(id),
  name TEXT NOT NULL, slug TEXT UNIQUE, district TEXT, created_at TIMESTAMP
);
CREATE TABLE neighbourhood_adjacency (
  from_id INT REFERENCES neighbourhood(id),
  to_id   INT REFERENCES neighbourhood(id),
  direction TEXT CHECK (direction IN ('N','S','E','W','NE','NW','SE','SW')),
  PRIMARY KEY (from_id, to_id)
);
CREATE TABLE price_snapshot (
  id SERIAL PRIMARY KEY,
  neighbourhood_id INT REFERENCES neighbourhood(id),
  source TEXT, property_type TEXT,
  price_eur NUMERIC, price_bgn NUMERIC,
  price_eur_sqm NUMERIC, price_bgn_sqm NUMERIC,
  overall_avg_eur_sqm NUMERIC,
  period_date DATE, scraped_at TIMESTAMP
);
```

### 3. ETL sequence
1. Seed `city`: `INSERT INTO city (name, slug) VALUES ('София', 'sofia')`
2. Seed `neighbourhood`: extract unique names+slugs from current snapshot
3. Seed `neighbourhood_adjacency`: manually curate ~50 Sofia pairs with directions
4. Load `price_snapshot`:
   - Current snapshot → direct insert (already has slugs)
   - Historical files → build slug_map first, then bulk insert

### 4. Neighbourhood adjacency
Needs **manual curation** — no data source for this.
Suggested approach: open a Sofia map, list ~40–50 key neighbourhoods, mark N/S/E/W/NE/NW/SE/SW neighbours.
Save as `db/seeds/sofia_adjacency.csv` then import.

---

## Re-running crawlers

```bash
cd /Users/gabe/Dev/bg-realestate-intel

# Current prices (run monthly)
python3 crawlers/imot_prices.py > data/raw/imot_bg/sofia_current_$(date +%Y-%m).jsonl

# Single missing year
python3 crawlers/imot_bg_history.py --start-year 2026 --end-year 2026 \
  --output-dir data/raw/imot_bg/sofia_history

# Transport (when Overpass is available)
python3 crawlers/fetch_transport.py --output data/raw/transport/sofia_transport.json

# Add another city (e.g. Varna — imoti.net city_id needs research)
# imot.bg history for Varna: update HISTORY_URL city slug in imot_bg_history.py
```

---

## Phase 3 — Builders (primary) + new-building projects (reusable, multi-city)

Reusable scraper framework in `crawlers/scraper_kit/` (one scraper per site under
`sites/`), normalizers in `crawlers/normalize/`, loaded by the idempotent
`backend/etl/run_phase3.py`. Safe to re-run on a schedule. Scrapers run under the
system `python3` (httpx + bs4); normalizers/ETL run under `backend/.venv`.

```bash
cd /Users/gabe/Dev/bg-realestate-intel

# --- Builders (national) — the primary pillar -------------------------------
# КСБ licensed-builder register (broad seed; verified working live):
python3 -m crawlers.scraper_kit.run --domain builders --site ksb
# Targeted: resolve specific developer names (e.g. from novitesgradi) to ЕИК:
python3 -m crawlers.scraper_kit.sites.ksb --names-file data/dev_names.txt
# (brra_opendata / aistn / nap enrichment scrapers: add under sites/, then --site all)

# --- New-building projects (per city) ---------------------------------------
python3 -m crawlers.scraper_kit.run --domain new_buildings --city sofia --site all

# --- Normalize (merge + cross-site dedup) -----------------------------------
python3 -m crawlers.normalize.builders --country bg
python3 -m crawlers.normalize.new_buildings --city sofia      # difflib entity resolution

# --- Refresh the headline crawl counter (data/stats/crawl_stats.json) -------
python3 -m crawlers.scraper_kit.stats

# --- Load to Postgres (idempotent; needs price ETL run first for city FKs) ---
cd backend && .venv/bin/python -m etl.run_phase3
```

API: `GET /api/stats` (the flex counter), `GET /api/builders[?q=&insolvent=&has_tax_debt=]`,
`GET /api/builders/{eik}`, `GET /api/cities/{slug}/projects`, `GET /api/neighbourhoods/{slug}/projects`.

Add a city: one entry in `crawlers/scraper_kit/cities.py`. Add a site: one file in
`crawlers/scraper_kit/sites/` exposing `SCRAPER`. Nothing else changes.

### Phase 3.5 — Ownership graph (builders ↔ owners ↔ managers)

`entity` (companies + persons) + `entity_edge` (directed ownership/management).
Source: **Papagal** (`papagal.bg`) per-ЕИК pages — companies link as `/eik/{eik}/…`,
persons as `/p/{hash}` (that hash = a stable `person_key`). Every node and edge
records its `source`. Scraper runs under system `python3`; ETL under `backend/.venv`.

```bash
cd /Users/gabe/Dev/bg-realestate-intel

# 1. Seed = the licensed builders' ЕИК (one per line).
python3 -c "import json;print('\n'.join(json.loads(l)['eik'] for l in open('data/normalized/builders/bg.jsonl')))" > data/seed_eiks_builders.txt

# 2. Scrape direct owners/managers (depth 1) for the seed -> data/raw/ownership/bg/papagal_<date>_<run-id>.jsonl
python3 -m crawlers.scraper_kit.sites.papagal --eiks-file data/seed_eiks_builders.txt
#   single ЕИК: python3 -m crawlers.scraper_kit.sites.papagal --eik 041044484

# 3. Load edges into Postgres (idempotent; reuses existing builder entities).
cd backend && .venv/bin/python -m etl.run_phase35
```

Depth-N (frontier BFS — owners-of-owners) is a larger, open-ended scrape: feed the
related companies' ЕИК discovered at depth 1 back into step 2 and re-run, repeating
to the desired depth. Edges/entities upsert idempotently, so re-runs are safe.

API (planned next): `GET /api/builders/{eik}/network?depth=N`, `GET /api/graph`.
`GET /api/builders/{eik}` already returns edge-derived `owners`/`managers`.

---

## Known issues / TODOs
- [ ] Phase 3 scrapers still to add: `brra_opendata` (ЕИК enrichment), `aistn` (insolvency),
      `nap` (tax debt), and new-building sites (`novitesgradi`, `bulgarianproperties`, `luximmo`)
- [ ] КСБ seed prefixes give broad (not exhaustive) coverage — extend `SEED_PREFIXES` or use
      `--names-file` for targeted developer resolution
- [ ] Stats UI: Neo-Memphis stat-tile count-up consuming `GET /api/stats` (frontend)
- [ ] Transport data incomplete — re-run `fetch_transport.py` when Overpass API accessible
- [ ] 6 neighbourhood geocodes outside Sofia bbox need manual correction (see coords file)
- [ ] `neighborhood_slug` null on all historical records — resolve in ETL via name lookup
- [ ] Neighbourhood adjacency table needs manual curation (not automatable without polygon data)
- [ ] Property type names may vary slightly in very old data (pre-2000) — validate during ETL

## Pushing research findings to production

Full procedure: `deploy/SYNC_API.md`.

```bash
python3 scripts/pb.py requests                    # what is waiting
python3 scripts/pb.py claim <id>                  # mark in_progress
python3 scripts/pb.py prod <eik>                  # what prod already holds
python3 scripts/pb.py push <id> <bundle.json>     # dry run — prints the diff
python3 scripts/pb.py push <id> <bundle.json> --apply
```

Bundles live in `data/bundles/<eik>_<stamp>.json`. `deploy/ENTITY_PUSH.md` is
deprecated — running it would erase API-written findings.
