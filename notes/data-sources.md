# Data Sources

## imot.bg — primary source

**URL pattern:**
- Current: `https://www.imot.bg/sredni-ceni`
- Historical: `https://www.imot.bg/sredni-ceni/prodazhbi-sofiya?year=YYYY&date=D.M.YYYY`

**What it provides:**
- Average sale prices per neighbourhood × property type
- Property types: едностаен / двустаен / тристаен + overall aggregate
- Weekly snapshots available via date dropdown
- Coverage: 1995–present, 130–141 Sofia neighbourhoods

**Technical notes:**
- Encoding: `windows-1251` (decode with `errors='replace'`)
- Table class: always `sredni-ceni-2025` (regardless of year queried)
- Current page has anchor links on neighbourhood names (slug extractable)
- Historical pages: NO links — neighbourhood names are plain text only
- No bot protection, no rate limiting observed

**Crawler:** `crawlers/imot_bg_history.py` (historical) + `crawlers/imot_prices.py` (current)

---

## OpenStreetMap / Overpass API — transport

**URL:** `https://overpass-api.de/api/interpreter`

**Status:** HTTP 406 returned on all endpoints during data collection (2026-05-26).
Geocoding via Nominatim succeeded (62/62 neighbourhoods found, 56 within Sofia bbox).

**When available, provides:**
- Metro route relations (M1, M2, M3, M4) with stop coordinates
- Tram route relations with stop coordinates
- Bus route relations (filtered by stop count for "major" routes)

**Crawler:** `crawlers/fetch_transport.py`

---

## Wikidata SPARQL — partial metro fallback

**URL:** `https://query.wikidata.org/sparql`

**What it provided (2026-05-26):** 8 metro stations (M1/M3/M4 partial)
- М4: Летище София, Искърско шосе, Дружба
- М1/М4: Стадион Васил Левски (interchange)
- М3: Хаджи Димитър, Театрална, Орлов мост

**Coverage:** Incomplete — not a reliable full source. Use as fallback only.

---

## Nominatim (OpenStreetMap geocoder) — neighbourhood centers

**URL:** `https://nominatim.openstreetmap.org/search`
**Rate limit:** 1 request/second max

**Results:** 62/62 Sofia neighbourhoods geocoded; 56 within Sofia bbox, 6 suspect:
- `lyulin-1`, `lyulin-7` — matched wrong "Люлин" location (probably a village)
- `yavorov`, `lagera`, `banishora`, `druzhba-1` — coordinates outside Sofia bbox

**File:** `data/raw/transport/sofia_neighbourhood_coords.json`

---

## NOT used in this phase

| Source | Why skipped |
|---|---|
| imoti.net | imot.bg has same years with better property types |
| GIS Sofia | Phase 2 (building permits + company data) |
| BRRA/CompanyBook | Phase 2 (company data) |
| ДНСК | Phase 2 (regulatory data) |
