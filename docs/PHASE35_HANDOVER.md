# Phase 3.5 — Ownership Graph: Session Handover

Written 2026-05-31. Resume pointer is `docs/PHASE3_RESUME.md`; full design/glossary is
`~/.claude/plans/orecestrate-a-couple-of-zazzy-dewdrop.md`. This file is the end-of-session
summary of what got built so a fresh session can continue without re-deriving context.

## What this session delivered

A full vertical slice of the **ownership graph** (builders ↔ companies ↔ people), data → API → UI,
all verified working. Builds on the completed Phase 3 (134 КСБ builders scraped + loaded).

### 1. Data model (DB)
- New tables: **`entity`** (nodes — companies AND persons) and **`entity_edge`** (directed
  ownership/management connections). `builder.entity_id` FK links the rich builder profile to its
  graph node. Dropped the empty `builder.owners`/`managers` JSON.
- A *builder* = `entity(kind='company', is_builder=true)`. Persons have no ЕИК → keyed by
  `person_key`. Edge natural key `(src, dst, relation, valid_from)`; carries `share_pct`, `role`,
  `is_current`, **`source`** (provenance on every node + edge — Gabe's explicit ask).
- Migration `d6354dfd3150` (reversible, tested). Migrated the 134 builders into entities.
- **Direct edges only** are stored; indirect = depth-bounded traversal (the "Дълбочина" control).

### 2. Scraper — Papagal (`crawlers/scraper_kit/sites/papagal.py`)
- Source = **papagal.bg** (chosen over BRRA, which is CAPTCHA/rate-limited).
- **Company mode** (`--eik` / `--eiks-file`): company page `/eik/{eik}/{hash}` (resolve via
  `/search_results/{eik}?type=company`) → owners (Собственост/Действителен собственик) + managers
  (Представляващи/Ръководни органи).
- **Person mode** (`--persons-file`, depth-2): person page `/p/{key}/{nonce}` (resolve via
  `POST /s {query:name}`, match exact `person_key`) → **every** company that person owns/manages,
  with **share %** and current/historical (`div.text-success` vs `text-danger`).
- **`person_key` = the `/p/` hash** — a stable per-person id that solves the "no public person id"
  dedup problem.
- Pure parsers `parse_company` / `parse_person` (9 stdlib-`unittest` tests vs saved fixtures in
  `crawlers/scraper_kit/tests/fixtures/`). Run crawler tests: `python3 -m unittest
  crawlers.scraper_kit.tests.test_papagal` (system python3 — backend `.venv` lacks bs4 + has no
  pytest for crawlers).
- `BaseScraper` gained a `file_tag` so company vs person runs don't overwrite each other's JSONL.

### 3. ETL (`backend/etl/entities.py`, `run_phase35.py`)
- `load_ownership` ingests BOTH record shapes (company `related[]` + `person_participations`) →
  entities + edges, idempotent (upsert on ЕИК / `person_key` / edge key). Helpers:
  `entity_for_company`, `entity_for_person`, `upsert_edge`, `backfill_builder_entities`.
- Runner: `cd backend && .venv/bin/python -m etl.run_phase35` (globs `data/raw/ownership/**`).

### 4. Graph API (`backend/app/routes.py`)
- `GET /api/builders/{eik}/network?depth=N` — ego network, depth-bounded **Python BFS** over direct
  edges + induced-edge set (portable, not a DB recursive CTE). Returns D3-ready `{center, nodes,
  edges}` — nodes have `depth`/`is_builder`, edges have `relation`/`share_pct`/`is_current`/`via`.
- `GET /api/graph?limit=N` — bounded global network (builders first).
- `GET /api/builders/{eik}` now derives `owners`/`managers` from edges (not the dropped JSON).

### 5. Frontend (Vue 3 + D3 v7, Neo-Memphis)
- `components/OwnershipGraph.vue` — interactive force-graph: drag, zoom, hover-highlight,
  click-to-navigate, **pre-settle + zoom-to-fit** (critical: 1251 nodes sprawl past the viewport
  without it). Nodes: builder=pink, company=blue, person=coral. Edges: ownership=teal (with %),
  management=grey, historical=dashed.
- `components/GraphLegend.vue`; reused `StatTile.vue`.
- `views/BuildersView.vue` (`#/builders`) — stats strip + type-ahead search + global constellation.
- `views/BuilderView.vue` (`#/b/{eik}`) — profile panel (owners/managers/projects + share pills) +
  depth-controlled ego graph.
- Routes added to `router.js`/`App.vue`; entry chip "Строители ↗" added to `Navbar.vue`.
- API client methods added in `api/index.js`: `stats`, `builders`, `builder`, `builderNetwork`,
  `graph`.

## Current data state (in local Postgres)
- **1251 nodes** = 134 builders + 886 other companies + 231 persons. **1966 edges** (1041
  ownership, 925 management). **100% have `source`** (`papagal`).
- Depth-1 = builders → direct owners/managers (0 builders missing). Depth-2 = expanded all 231
  persons → 886 more companies. Biggest hubs: Огнян Донев (77 companies), Венцислав Стоев (76),
  Даниел Гаргов (65).
- Ad-hoc add this session: **Билд Инвест България** (ЕИК 203539318) + 3 people (see open gap below).

## Tests — all green
- **46 backend** (`cd backend && .venv/bin/python -m pytest -q`)
- **9 crawler** (`python3 -m unittest crawlers.scraper_kit.tests.test_papagal`)

## How to run
```bash
./dev.sh    # backend :8000 + frontend :5173
# http://localhost:5173/#/builders   ·   /#/b/101055748 (МОНОЛИТСТРОЙ ego view)
```

## OPEN GAP — the next thing to build (Gabe hit this live)
**Search/browse only covers the 134 licensed builders, not all entities.** Gabe searched for
"БИЛД ИНВЕСТ БЪЛГАРИЯ" (ЕИК 203539318) — a *developer/investor*, not a КСБ builder — and couldn't
find it. We scraped + loaded it on demand, but it's still not searchable because `/api/builders`
and `/b/{eik}` are builder-only. **Fix:** add `GET /api/entities?q=` (search across `entity`) +
`GET /api/entities/{eik}/network`; point the search box + ego page at entities with a "licensed
builder" badge for the КСБ subset. This turns it into "search any company/person in the graph."

## Other next steps (optional)
- Depth-3 BFS (diminishing returns, much larger scrape — feed depth-2's new company ЕИК back into
  `--eiks-file`).
- КСБ trust signals (insolvency / tax-debt) into node styling + builder pills (need `aistn`/`nap`
  scrapers).
- Global-view polish: cluster labels, edge-type/current filters.

## Gotchas / conventions
- Scrapers run under **system python3** (httpx + bs4, no DB); ETL/tests/API under **backend/.venv**
  (sqlalchemy, no bs4). They can't share an interpreter.
- Papagal is third-party — rate-limited at 1.5s/req; be polite. ~12 persons of 231 didn't resolve
  by name search (acceptable).
- Stray verification screenshots in repo root (`builders-global*.png`, `builder-ego.png`,
  `home-with-link.png`) + `data/raw/ownership/bg/papagal_adhoc_*.jsonl` — safe to delete.
- **Nothing committed.** All work is in the working tree on branch `feat/neighbourhood-deep-dive`;
  local DB is migrated + loaded. Capital from Papagal is shown in € and stored as BGN via the peg.
