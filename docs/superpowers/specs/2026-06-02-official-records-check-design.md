# Official-records check protocol — design

**Date:** 2026-06-02
**Status:** Approved (brainstorming → ready for implementation plan)
**Scope:** Add an "official" evidence tier with real data, starting with court acts for
АРТЕКС ИНЖЕНЕРИНГ АД (ЕИК 175155346).

---

## Context & problem

The entity evidence aggregator (`entity_signal`) has three tiers — **official** (public
registers / court), **community** (forum), **web** (search hits). АРТЕКС currently shows
**0 official, 5 community, 6 web**. Yet the Златен век court saga *is* present — it just
arrived as **news articles** and so landed in the lowest-confidence **web** tier, not as
primary court records.

Root cause: there is **no scraper feeding the official tier**. The plumbing already
exists and is unused —
- `etl/load_signals.load_registry` ingests `data/raw/signals/<scope>/registry_*.jsonl`,
  matching by **exact ЕИК** → `tier="official"`, and is wired into `etl/run_signals.py`.
- `crawlers/normalize/builders.py` already defines source slots `insolvency_flag, cases ←
  aistn` and `tax_debt_bgn ← nap`, merged per-ЕИК into the builder record. Never built.
- `EntityView.vue` already renders an "Official records" group and an `INSOLVENCY` pill.

So this work is **producing data for existing rails**, not new model/API/UI.

### Feasibility recon (2026-06-02, read-only)

| Source | Reachable | Gives | Verdict |
|---|---|---|---|
| **legalacts.justice.bg** (published court acts) | ✅ server-rendered POST form | Full court decisions, searchable by party name; acts cite the legal entity's ЕИК | **Image CAPTCHA (`/captcha.ashx`) on every search.** Not bulk-automatable. Best source for the Артекс litigation. |
| **BRRA / Търговски регистър** (portal.registryagency.bg) | ✅ | Company status, insolvency, capital, owners | Free guest search effectively gated; clean route is the registered TR API. Doesn't surface Артекс (it is solvent). |
| **data.egov.bg** (open data) | ⚠️ 403 to bot | Bulk datasets | Needs proper API access; deferred. |
| **ВАС** (vas.bg) | ✅ | Supreme Administrative Court only | Partial; deferred. |
| **ДНСК** (construction-control orders) | ✅ (SSL workaround) | stop/demolition заповеди | Keyed by site/object, not ЕИК; messy; deferred. |
| **Papagal** (already integrated) | ✅ no CAPTCHA | Company `Статус` already scraped | Pragmatic CAPTCHA-free status source. |

**Conclusion:** the richest court source is CAPTCHA-walled. We will **not** auto-solve a
government CAPTCHA (detection-evasion / ToS). The honest shape is two-speed:
human-assisted court acts for a flagged shortlist + automatic CAPTCHA-free status for all.

---

## Decisions (locked with user)

1. **Matching strictness:** official-tier records kept **only when the company ЕИК appears
   in the source document** (ЕИК-confirmed). Preserves the existing "official = exact ЕИК"
   invariant; zero wrong-entity risk; matches the project's defamation-safe framing.
2. **Court-acts capture:** Playwright browser, **human solves each CAPTCHA**, run on a
   **curated shortlist** of ЕИК (Артекс first) — never "all companies".
3. **Status check:** automatic, CAPTCHA-free, **all companies**, via the **existing
   Papagal** scraper (v1). Primary-source BRRA API is a documented future upgrade.
4. **No** CAPTCHA auto-solving, solver services, or scraping gated sources without a human.

---

## Architecture

Two independent components on existing pipelines. Build A first (it is the "test on
Артекс" gate), then B.

### Component A — Court-acts assistant (`legalacts`), human-solved

New scraper-kit site `crawlers/scraper_kit/sites/legalacts.py`, driven through a **real
Playwright browser**, run over a hand-maintained shortlist file of ЕИК.

Flow per `(eik, name)`:
1. Open legalacts search; fill `KeyWord` = company name (and `IsLuceneInUse`).
2. **Block and prompt the operator to type the visible CAPTCHA code**; submit on their input.
3. Within the same session, scrape the result list and follow each act link. If pagination
   re-prompts for a CAPTCHA, **pause again** (never auto-solve).
4. **ЕИК-confirmation filter:** keep an act only if `eik` occurs in the act text. Drop the rest.
5. Emit `data/raw/signals/<scope>/registry_<YYYY-MM-DD>.jsonl` rows:
   `{matched_eik, url, title, snippet, source_site:"legalacts", observed_date, scraped_at}`.

Then `cd backend && .venv/bin/python -m etl.run_signals` → `load_registry` →
**official-tier** `entity_signal`. `EntityView.vue` "Official records" group renders it.
**No backend/frontend code change.**

Honest constraints baked in: low request volume, one human CAPTCHA per company, shortlist-only.

### Component B — Automatic status check (all companies), CAPTCHA-free

Extend the **existing** `crawlers/scraper_kit/sites/papagal.py` to derive insolvency /
liquidation from the `Статус` text it already scrapes (status contains
`несъстоятелност`/`ликвидация`/`в ликвидация` → `insolvency_flag=true`). The record flows
through `normalize.builders` (`status`/`insolvency_flag` slots) → `load_phase3` →
`Builder.insolvency_flag`. The `INSOLVENCY` pill already exists.

Optional: also emit an official-tier `registry_*.jsonl` row for a confirmed insolvency so
it appears in the evidence feed (ЕИК-confirmed by construction).

- **NAP tax-debt (`nap`): deferred** — not reliably public by ЕИК. Slot stays wired, unbuilt.
- **BRRA TR-API primary source: future upgrade**, not in this scope (needs a contract).

---

## Components & boundaries

| Unit | Responsibility | Input → Output | Depends on |
|---|---|---|---|
| `legalacts.py` | Drive browser, human CAPTCHA, scrape acts | shortlist ЕИК → `registry_*.jsonl` | Playwright, base scraper |
| ЕИК-confirm filter (pure fn) | keep acts citing the ЕИК | act text + eik → bool | — |
| record shaper (pure fn) | act → registry row | dict → dict | — |
| papagal status→flag (pure fn) | derive insolvency from status | status str → bool | — |
| (existing) `load_registry` / `run_signals` | registry rows → official signals | jsonl → DB | unchanged |
| (existing) `normalize.builders` / `load_phase3` | merge + load builder fields | jsonl → DB | unchanged |

The pure functions are unit-tested without network (mirroring `tests/test_papagal.py`,
`tests/test_match.py`).

---

## Data flow

```
shortlist ЕИК ─► legalacts.py (browser, human CAPTCHA)
                   └─ ЕИК-confirm filter ─► data/raw/signals/<scope>/legalacts_<date>_<run-id>.jsonl
                                              └─ run_signals → load_registry ─► entity_signal (tier=official)
                                                                                  └─ /api/entities/{key} → EntityView "Official records"

all builders ─► papagal.py (status) ─► data/raw/builders/bg/papagal_<date>_<run-id>.jsonl
                   └─ status→insolvency_flag
                        └─ normalize.builders → load_phase3 ─► Builder.insolvency_flag ─► INSOLVENCY pill
```

---

## Error handling & idempotency

- **CAPTCHA / no results / timeout:** the assistant logs and continues to the next ЕИК;
  pagination re-prompt → pause for human, never bypass.
- **Idempotent:** `entity_signal` upserts on `(url, matched_name)`; builder fields upsert
  on ЕИК. Re-runs add nothing new. ЕИК-confirm filter makes false positives structurally
  impossible in the official tier.
- **Provenance:** every official row carries `source_site` + `url` + `observed_date`.

---

## Out of scope (YAGNI)

NAP tax-debt scraper; BRRA TR-API integration; ДНСК order matching; ВАС-specific adapter;
any change to the signals data model, API, or `EntityView.vue`. Court-acts automation
across all companies (CAPTCHA makes it impossible without bypass).

---

## Validation (end-to-end)

1. **A on Артекс (175155346):** run the assistant, solve the CAPTCHA; confirm
   `registry_*.jsonl` has ≥1 ЕИК-confirmed act; `run_signals`; open `/e/175155346` →
   "Official records" group now populated (the Златен век acts). **This is the go/no-go gate.**
2. If good → run A on the next flagged developers (shortlist).
3. **B:** extend Papagal, re-run builder ETL on a known-insolvent test ЕИК; confirm the
   `INSOLVENCY` pill lights up.
4. `cd backend && .venv/bin/pytest` (new pure-fn tests + existing suite green).
