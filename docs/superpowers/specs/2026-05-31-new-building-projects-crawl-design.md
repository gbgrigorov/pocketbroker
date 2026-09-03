# New-Building Projects — Overnight Crawl Design

**Date:** 2026-05-31 (spec) · **Scheduled run:** 2026-06-01 02:45 local
**Phase:** 3 (new buildings — the secondary pillar that feeds the builder graph)
**Status:** Approved design, awaiting spec review.

---

## Goal

Collect Sofia new-construction project listings from three sites, dedup them into
canonical project records, and load them into Postgres — unattended, overnight.
Gabe wakes up to projects in the DB and a telemetry line at `GET /api/stats`.

**Operating constraint:** This spec is written in-session now to spend minimal
tokens. **No scrapers are written tonight.** All implementation (site research →
scrapers → normalize → ETL → report) happens when the scheduled session fires at
02:45 on 2026-06-01, after the token budget resets.

## Target sites (all three, confirmed)

| Site | URL | Segment | Notes |
|------|-----|---------|-------|
| novitesgradi.bg | novitesgradi.bg | BG new-build, broad | Cleanest map to schema; primary source |
| bulgarianproperties.com | bulgarianproperties.com | Resale + new-build | Filter to `ново строителство` + Sofia |
| luximmo.bg | luximmo.bg | Luxury/premium | Smaller; high price points; overlaps known КСБ builders |

## Non-goals (YAGNI)

- No per-building cadastre register (КККР) — explicitly deferred in Phase 3.
- No price-history for projects — one snapshot is enough this run.
- No new DB tables — `new_building` / `new_building_source` already exist.
- No frontend work.

---

## Architecture

Reuses the existing, proven pipeline. Nothing new structurally.

```
3 site scrapers (BaseScraper subclasses, system python3 + httpx + bs4)
    → data/raw/new_buildings/<site>/sofia.jsonl   (one raw listing per line)
crawlers/normalize/new_buildings.py  (stdlib difflib cross-site dedup)
    → data/normalized/new_buildings/sofia.jsonl
backend/etl/run_phase3.py  (idempotent upsert on canonical_key)
    → Postgres: new_building + new_building_source + crawl_run
[bonus] crawlers/scraper_kit/sites/ksb.py --names-file
    → resolve developer names → ЕИК → link new_building.developer_id to builder
```

### Environment split (existing convention, must hold)

- **Scrapers + normalizer:** system `python3` (has `httpx` + `bs4`).
- **ETL + tests:** `backend/.venv/bin/python` (has SQLAlchemy; no bs4).
- `pytest` must stay green: `cd backend && .venv/bin/python -m pytest -q`.

---

## Components

### 1. Site scrapers — `crawlers/scraper_kit/sites/{novitesgradi,bulgarianproperties,luximmo}.py`

Each is a `BaseScraper` subclass with `site=<name>`, `domain="new_buildings"`,
`rate_limit_s=1.0`. Each yields dict records and writes to
`data/raw/new_buildings/<site>/sofia.jsonl`.

**Output contract — every record MUST emit exactly the normalizer's
`CANONICAL_FIELDS`:**

```json
{
  "source": "novitesgradi",
  "source_url": "https://novitesgradi.bg/...",
  "city": "sofia",
  "name": "Резиденс Изток",
  "developer_name": "Главболгарстрой АД",
  "neighbourhood": "Изток",
  "neighbourhood_slug": "iztok",
  "price_eur_sqm_min": 1400,
  "price_eur_sqm_max": 2000,
  "completion_date": "2026-09",
  "status": "under_construction",
  "scraped_at": "2026-06-01T02:45:00Z"
}
```

- `status` ∈ `{planned, under_construction, completed, unknown}` (normalize at source).
- `neighbourhood_slug`: best-effort map to the 62 known slugs; `null` if no match
  (ETL/normalizer can resolve later — same pattern as historical prices).
- Any field genuinely absent on a site → `null`. Never invent values.
- Encoding: BG sites are often Windows-1251 — decode with `errors="replace"`.

**Per-scraper research (step 0, at run time):** fetch the Sofia listings page,
read the HTML, find listing-card selector + pagination + field locations. Save one
sample page to `data/fixtures/new_buildings/<site>/listing_sample.html`. Write 1–2
parser unittests against the fixture (system python3, `unittest`), mirroring the
КСБ/Papagal test convention.

**Isolation requirement:** a site that returns 0 records or 4xx/5xx must log and
exit cleanly WITHOUT aborting the other two. Each site writes its own raw file.

### 2. Normalizer — `crawlers/normalize/new_buildings.py` (already exists)

Run as-is: `python3 -m crawlers.normalize.new_buildings`. Groups raw listings by
`_norm_name` similarity ≥ 0.86, merges price ranges, keeps every `source_url`,
picks best non-null fields. No change expected; only touch it if a real bug
surfaces during the run.

### 3. ETL — `backend/etl/run_phase3.py` (already wired)

`cd backend && .venv/bin/python -m etl.run_phase3`. Calls
`load_new_buildings(session, records, "sofia", report)` per normalized file;
idempotent upsert on `canonical_key`. Crawl telemetry → `crawl_run` via the
`*.stats.json` manifests the framework writes. Safe to re-run.

### 4. Bonus — developer → ЕИК linkage

After ETL, collect distinct `developer_name`s, write to a temp names file, run
`python3 -m crawlers.scraper_kit.sites.ksb --names-file <file>` to resolve to ЕИК,
then link `new_building.developer_id` to the matching `builder`. If КСБ has no
match, leave `developer_id` null (the developer simply isn't a registered builder).
This is best-effort; skip if time/tokens run short.

---

## Run sequence (what the 02:45 session executes, in order)

1. Confirm clock is ≥ 02:45 2026-06-01 and token budget reset; else reschedule.
2. For each site: research → write scraper + fixture test → run scraper.
3. Run all three scrapers (isolated; failures don't cascade).
4. Run normalizer → `data/normalized/new_buildings/sofia.jsonl`.
5. Run ETL (`run_phase3`).
6. Bonus: developer → ЕИК linkage.
7. `cd backend && .venv/bin/python -m pytest -q` (must stay green).
8. Write a morning report (below) + update HANDOVER.md active tasks → done.

## Success criteria

- ≥ 1 site yields > 0 records (ideally all 3).
- `data/normalized/new_buildings/sofia.jsonl` exists with deduped projects.
- Rows present in `new_building`; `GET /api/stats` reflects the new count.
- `pytest` green. No PII / VPS IP committed.

## Error handling

- **Site HTML changed / 0 records:** log, save the fetched HTML for morning
  debugging, continue. Report which sites failed.
- **Site blocks us (403/429):** back off, single retry, then skip. Aggressive
  posture is sanctioned, but don't hammer past a hard block.
- **Normalizer/ETL exception:** stop the pipeline, preserve raw + normalized files,
  write what failed to the report so nothing is silently lost.
- **DB unreachable:** leave normalized JSONL on disk; report that ETL is pending.

## Morning report (printed + appended to HANDOVER.md)

```
New-buildings overnight crawl — 2026-06-01
  novitesgradi:        N raw
  bulgarianproperties: N raw
  luximmo:             N raw
  → deduped to:        Z unique projects
  → loaded to DB:      Z (X new, Y updated)
  developer→ЕИК linked: K of M developers
  pytest: PASS/FAIL
  Sites that failed:   <list or none>
```

## Open risk

Parsers are written blind against tonight's-unknown HTML. Mitigation: research
step fetches live HTML first, fixtures capture it, tests assert against it. If a
site is fundamentally unscrapable (heavy JS / hard block), it's reported as failed
and the other two still deliver — no all-or-nothing.
