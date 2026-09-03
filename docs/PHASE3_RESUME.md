# Phase 3 — Resume Here

Quick-start pointer for resuming the builders / ownership-graph build.

## Status (as of 2026-05-31)

**Done + verified (38 tests green):**
- Reusable multi-city scraper framework — `crawlers/scraper_kit/` (base, cities, run, stats, sites/)
- Cross-site normalizers — `crawlers/normalize/` (builders by ЕИК; new_buildings via stdlib difflib)
- Schema + migration — `builder`, `new_building`, `new_building_source`, `crawl_run`
- Idempotent ETL — `backend/etl/run_phase3.py`; API — `/api/stats`, `/api/builders[/{eik}]`, projects
- **КСБ scraper** (`sites/ksb.py`) — LIVE-VERIFIED: scraped 134 real builders → Postgres → API
- **Phase 3.5 Step 1 — the data model (DONE)**: `entity` + `entity_edge` tables (models +
  migration `d6354dfd3150`); `builder.entity_id` FK; the 134 КСБ builders backfilled into company
  entities (`is_builder`); dropped redundant `owners`/`managers` JSON. Helpers in
  `backend/etl/entities.py` (`entity_for_builder`, `backfill_builder_entities`, idempotent
  `upsert_edge`); `load_builders` now mirrors each builder into a node; `/api/builders/{eik}`
  derives owners/managers from edges. Tests: `backend/tests/test_phase35_entities.py`.

- **Step 2 — ownership scraper (DONE, Papagal)**: `crawlers/scraper_kit/sites/papagal.py`.
  Company mode (`--eiks-file`) → owners/managers; person mode (`--persons-file`, depth-2)
  → every company a person owns/manages, with **share %** + current/historical. Pure parsers
  `parse_company` / `parse_person` (9 unittest tests vs saved fixtures). URL facts: companies
  `/eik/{eik}/{hash}` (resolve via `/search_results/{eik}?type=company`); persons `/p/{key}/{nonce}`
  (resolve via `POST /s {query:name}`, match exact `person_key`). **`person_key` = the `/p/` hash**
  (stable, solves person dedup). Current = `div.text-success`, historical = `div.text-danger`.
- **Step 3+4 — ownership ETL (DONE)**: `etl/entities.py::load_ownership` ingests both record
  shapes → `entity` + `entity_edge`, idempotent, **`source` on every node/edge**. Runner
  `etl/run_phase35.py`. Depth-1 loaded: 134 companies + 231 persons + 370 edges, 0 missing.
  Depth-2 person scrape (231 persons) in progress / loading.

**Next (not built):**
1. Graph API: `/api/builders/{eik}/network?depth=N` (recursive CTE) + bounded `/api/graph`.
2. Frontend: D3 v7 force-graph (global + ego/depth) + Neo-Memphis stats count-up tile.

## Where the detail lives
- Full plan + Phase 3.5 ownership-graph design + **glossary**: `~/.claude/plans/orecestrate-a-couple-of-zazzy-dewdrop.md`
- Auto-memory: `~/.claude/.../memory/phase3-builders.md` (+ `MEMORY.md` index)
- Commands: `RUNBOOK.md` → "Phase 3" section

## Conventions
- Scrapers run under **system python3** (httpx + bs4). ETL/tests under **backend/.venv**.
- `pytest` must stay green: `cd backend && .venv/bin/python -m pytest -q`
- Idempotent upserts on natural keys (`builder.eik`, `new_building.canonical_key`, edges).

## Open decisions / gates (need user OK)
- Bulk downloads (BRRA dump) + long live scrapes — ask before running.
- VPS deployment — prep only; user drives `ssh`/`git push` (never commit the VPS IP).
- Person dedup has a hard data ceiling (no public unique person id) — merge conservatively.
- Still unanswered by user: (a) go-ahead for BRRA bulk download + long scrapes? (b) does
  "finalize" include VPS deploy or stay local-complete?

## Key decisions (locked with Gabe)
- **Builders are the primary pillar** (who's behind them, budget, did they go bust / owe taxes /
  cheat buyers). New buildings secondary; per-building cadastre register deferred.
- **Free / open-data sources only.** **Aggressive** scraping posture (incl. КАИС).
- **Reusable, multi-city** framework: per-site scraper → normalizer (cross-site dedup) →
  idempotent ETL. City is a parameter; builders are national (scope `bg`).
- **Separate tables** for builders vs new buildings.
- A **crawl stats counter** ("X GB scanned · Y data points · Z builders") is a wanted presentation
  feature → `GET /api/stats`, persisted in `crawl_run`.
- Two join keys: **ЕИК** (company id), **КККР** (cadastral building id).

## Phase 3.5 data model (the next thing to build)
Replace the empty `builder.owners`/`managers` JSON with a real graph:
- **`entity`** (nodes — companies AND persons): `id, kind('company'|'person'), eik (nullable,
  unique when present), name, name_normalized, person_key (persons only), is_builder, legal_form,
  status, address, capital_bgn, first_seen, last_seen, source`. A builder = entity flagged
  `is_builder`.
- **`builder`** stays as the rich profile extension → add `builder.entity_id` FK; migrate the 134
  existing rows into `entity`. Keep ksb_category, financials, insolvency_flag, tax_debt_bgn.
- **`entity_edge`** (connections): `id, src_entity_id, dst_entity_id, relation('ownership'|
  'management'), share_pct, role, valid_from, valid_to, is_current, source`. Direction: ownership →
  src owns dst; management → src manages dst. Natural key `(src,dst,relation,valid_from)`; index
  src & dst.
- `new_building.developer_id` already links projects → builder (keep).
- **Direct vs indirect is NOT stored** — only direct edges; indirect = recursive-CTE traversal
  bounded by a `depth` param (the "Дълбочина: N нива" control).

## Glossary (shared vocabulary)
| Term | Meaning |
|------|---------|
| Entity | Any node — a company or a person. |
| Company | Entity with an ЕИК. |
| Person (физическо лице) | Entity with no ЕИК; keyed by `person_key`. |
| Builder | A company flagged `is_builder` (in КСБ). A role on a company. |
| Developer / Investor (инвеститор) | The company behind a specific new building. |
| Edge / Connection | A directed relationship between two entities. |
| Ownership (собственост) | src owns dst; carries `share_pct` (дял). |
| Management (управление) | src (person) manages dst (company); carries `role`. |
| Direct / Indirect | one edge (1 hop) / a path of 2+ edges. |
| Depth (дълбочина) | hops traversed from the focus entity. |
| Ego-network | subgraph around one entity up to depth N (the single-builder page). |
| Current vs Historical (историческа връзка) | `is_current`; past links rendered dashed. |
| UBO (действителен собственик) | the person at the end of an ownership chain. |
| Project (`new_building`) | a development, linked to a builder via `developer_id`. |
