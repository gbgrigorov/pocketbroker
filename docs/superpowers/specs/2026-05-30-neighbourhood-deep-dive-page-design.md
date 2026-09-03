# Neighbourhood Deep-Dive Page — Design Spec

**Date:** 2026-05-30
**Status:** Approved design (pending written-spec review)
**Design mockup:** [design/Neighbourhood single page.png](../../../design/Neighbourhood%20single%20page.png)

## Context

The platform currently has a single screen: the Sofia bubble map (home page). Users can see
neighbourhood-level average €/m² but cannot drill into one neighbourhood. This spec adds a
**neighbourhood deep-dive page** — an investment-analysis view for a single neighbourhood
covering price & rent trends, an investment-quality verdict (yield, price-to-rent), affordability
(cost in gold, minimum salaries), and a mortgage calculator, plus a geographic "neighbour ring"
visualisation.

Roughly half the requested content depends on data not yet collected. Per the agreed sequencing,
we **collect the low-effort data first, add DB tables, then build the page**. The hard data
(amenity/area/green-ratio stats panel) is **deferred** and tracked in Trello card
[mNuJAYqO](https://trello.com/c/mNuJAYqO).

## Scope & sequencing

1. **Part A — Data collection** (rent, gold, minimum wage)
2. **Part B — Database** (additive migrations + ETL)
3. **Part C — API**
4. **Part D — Frontend page + home-page entry button**

**Out of scope (deferred):** the stats panel (total area, building-vs-green ratio, hospitals,
kindergartens, schools, supermarkets). Blocked on the Trello research ticket. The page reserves
a visual slot for it marked "coming soon".

---

## Part A — Data collection

### A1. Rent (imot.bg) — extend existing crawlers, do not write new ones
imot.bg exposes rent averages with the **same structure and full history** as sales, at the
`naemi-` path (confirmed by user): `https://www.imot.bg/sredni-ceni/naemi-sofiya?year=1995&date=21.10.1995`.

- **[crawlers/imot_prices.py](../../../crawlers/imot_prices.py)** (current snapshot): parametrize the
  hardcoded `prodazhbi-` URL ([line 302](../../../crawlers/imot_prices.py#L302)) and the hardcoded
  `transaction_type: "sale"` ([line 268](../../../crawlers/imot_prices.py#L268)) so it can run for
  `sale` or `rent`. Output rent rows with `transaction_type: "rent"`.
- **[crawlers/imot_bg_history.py](../../../crawlers/imot_bg_history.py)** (history): parametrize
  `HISTORY_URL` ([line 37](../../../crawlers/imot_bg_history.py#L37)) `prodazhbi-sofiya` →
  `naemi-sofiya`. The parser (table class `sredni-ceni-2025`) is unchanged. Output to
  `data/raw/imot_bg/sofia_history_rent/YYYY_october.jsonl` and tag `transaction_type: "rent"`.
- Encoding (Windows-1251, `errors='replace'`), rate limiting, and the closest-to-Oct-15 date
  selection all carry over unchanged.
- **First implementation step:** run a single-year smoke test against the rent URL to confirm the
  table parses before backfilling 31 years.

### A2. Gold prices — one-time historical fetch
Monthly gold price in **EUR per gram**, ~1995→present, from a public source (free historical
gold price CSV/API). Output `data/raw/gold/gold_eur_per_gram.jsonl` with `{period_date, price_eur_per_gram, source}`.

### A3. Minimum wage — small static dataset
Bulgaria's **minimum monthly wage** by year (~1995→present, NSI / public record). Output
`data/raw/macro/bg_min_wage.jsonl` with `{year, amount_bgn, amount_eur, source}`. Convert BGN→EUR
at the fixed peg 1.95583 (consistent with existing crawler convention).

---

## Part B — Database (additive, no breaking changes)

All of the below ship in **one Alembic migration** (`down_revision = '2575703c0c0e'`), following
the existing pattern in [backend/alembic/versions/](../../../backend/alembic/versions/).

### B1. `price_snapshot` — rent column + EUR-only + index
- **Add** `transaction_type TEXT` (`'sale'` | `'rent'`, nullable) to
  [price_snapshot](../../../backend/app/models.py#L45). This reuses the existing ETL and the
  `/prices` endpoint instead of a parallel rent table. Backfill existing rows to `'sale'`. The
  loader always sets it (`rec.get("transaction_type", "sale")`).
- **Drop** the redundant BGN columns `price_bgn` and `price_bgn_sqm`. Because BGN is a fixed
  multiple of EUR (`× 1.95583`), they carry no extra information — `price_bgn` was just
  `price_eur × peg` computed by the crawler. We persist **EUR only**
  (`price_eur`, `price_eur_sqm`, `overall_avg_eur_sqm`); BGN, if ever displayed, is derived in the
  UI. Raw JSONL is untouched; the ETL simply stops loading the two BGN fields (remove them from
  `_PRICE_FIELDS` at [load.py:19](../../../backend/etl/load.py#L19)). No real data loss — the ETL
  rebuilds from raw and the values are fully reconstructable.
- **Add index** `(neighbourhood_id, transaction_type, period_date)` — the exact filter used by
  `/prices?transaction_type=…` and the apartment table.

### B2. New reference tables (standalone, no FK; joined by date/year in app logic)
```sql
CREATE TABLE gold_price (
  id SERIAL PRIMARY KEY,
  period_date DATE NOT NULL,
  price_eur_per_gram NUMERIC NOT NULL,
  source TEXT
);                              -- UNIQUE index on period_date (idempotent reloads)
CREATE TABLE min_wage (
  id SERIAL PRIMARY KEY,
  year INT NOT NULL UNIQUE,
  amount_bgn NUMERIC,
  amount_eur NUMERIC,           -- amount_bgn kept here as source-of-record macro figure
  source TEXT
);
```
(Note: `min_wage.amount_bgn` is retained because the minimum wage is *officially set* in BGN —
here BGN is the authoritative figure, not a derived one, so both are stored.)

### B3. ETL
Extend [backend/etl/load.py](../../../backend/etl/load.py):
- Rent flows through the existing `current_records` / `history_records` iterables (same row shape +
  `transaction_type: "rent"`); `_price_snapshot` gains one line for `transaction_type`. Historical
  rent `neighborhood_slug` is null — resolved via the same `NameResolver` name→slug map already
  used for historical sale prices ([load.py:95](../../../backend/etl/load.py#L95)).
- Add `load_gold` / `load_min_wage` loaders + `gold_loaded` / `min_wage_loaded` on `LoadReport`.
- [run_etl.py](../../../backend/etl/run_etl.py) globs the new rent / gold / min-wage raw files.

---

## Part C — API

The year slider must recompute many metrics. **Strategy: load full series once per page, compute
per-year reactively on the client** (avoid refetch on every slider tick).

- **Extend** [`/api/neighbourhoods/{slug}/prices`](../../../backend/app/routes.py#L45): accept
  `?transaction_type=sale|rent` (default `sale`), and return series **per `property_type`**
  (едностаен / двустаен / тристаен) in addition to the overall average, so the apartment table can
  use room-specific €/m².
- **New** `GET /api/neighbourhoods/{slug}` — name, district, lat/lon.
- **New** `GET /api/neighbourhoods/{slug}/neighbours` — directional neighbours for the bubble
  cluster (see D2), each with slug, name, direction, and its €/m² series (or latest value).
- **New** `GET /api/reference/gold` — full gold EUR/gram series.
- **New** `GET /api/reference/min-wage` — full min-wage series.
- Add matching wrappers in [frontend/src/api/index.js](../../../frontend/src/api/index.js).

---

## Part D — Frontend

### D1. Routing & entry point
- Add **`vue-router`** (not currently installed). Routes: `/` (existing map) and `/n/:slug`
  (deep-dive). Refactor [App.vue](../../../frontend/src/App.vue) to host `<router-view>`; move the
  current map layout into a `MapView`/home view.
- Add a **button in the home-page neighbourhood detail section**
  ([DetailPanel.vue](../../../frontend/src/components/DetailPanel.vue)) linking to `/n/:slug` for the
  active neighbourhood. (Per user: "just add a button under the neighbourhood section for now.")

### D2. Section 1 — Year slider
Scrubs 1995→2026. Drives a reactive `selectedYear` in a page-level Pinia store / component state;
all sections derive their displayed values from the loaded series at that year.

### D3. Section 2 — Bubble cluster (matches mockup)
New component `NeighbourCluster.vue` (custom D3, **not** the Leaflet `BubbleMap`).
- Center circle = current neighbourhood; surrounding circles = nearest neighbour in each compass
  sector (N, S, E, W, NE, NW, SE, SW), computed from `lat/lon`: bin candidate neighbourhoods by
  bearing from center into 8 sectors, pick the nearest in each. No adjacency table needed.
- Circle **radius ∝ €/m²** at `selectedYear`; place each at its compass position around the center;
  apply D3 force collision so circles touch but do not overlap.
- Neo-Memphis styling (flat fills, 2px black stroke, hard shadow). Center = pink `#FF3366`,
  neighbours = teal `#00D4CC`. Click a neighbour → `router.push('/n/<slug>')`.

### D4. Section 3 — Trend charts
Reuse [PriceChart.vue](../../../frontend/src/components/PriceChart.vue) twice: **Price/m² history**
and **Rent/m² history**, side by side. (Generalise its prop label/colour if needed.)

### D5. Section 4 — Apartment market table
Standard sizes: **1-room = 40 m², 2-room = 60 m², 3-room = 100 m²** (constant across all
calculations). For the selected year, per size:
- **Total sale price** = sale €/m² (room-specific) × area
- **Monthly rent** = rent €/m² (room-specific) × area
- **Gross yield** = (monthly rent × 12) ÷ total sale price
- **Price-to-rent ratio** = total sale price ÷ (monthly rent × 12), colour-coded:
  ≤15 great · 15–20 caution · 20–25 poor · >25 disastrous (design tokens).

### D6. Section 5 — Affordability table (recomputes with slider)
Per apartment size, at `selectedYear`:
- **Cost in gold** = total sale price (EUR) ÷ gold EUR/gram at that date → grams (display kg).
- **Minimum salaries to buy** = total sale price ÷ (min monthly wage EUR at that year).
- **Golden standard** column = the healthy **price-to-rent benchmark (~15)** shown as a fixed
  reference, so each row's actual ratio is compared against the ideal.

### D7. Section 6 — Mortgage panel (Bulgarian rates)
Editable inputs with researched defaults (**to confirm with user**):
- Down payment: **15%** (Sofia LTV up to 85%)
- Annual interest: **2.9%** fixed
- Term: **30 years**

Outputs: minimum down payment (EUR), monthly payment (standard amortisation formula), and minimum
net monthly income the bank requires (payment ≤ ~50% of net income → `min_income = payment / 0.5`).

### D8. Deferred stats slot
Reserve a card/section labelled "Neighbourhood stats — coming soon" where the amenity/area panel
will go once the Trello research resolves.

---

## Computations reference

- Currency peg: 1 EUR = 1.95583 BGN.
- Gross yield = annual rent ÷ price. Price-to-rent = price ÷ annual rent (= 1/yield).
- Mortgage monthly payment: `P · r(1+r)^n / ((1+r)^n − 1)`, `r` = monthly rate, `n` = months.

## Design system
Neo-Memphis tokens from [frontend/src/styles/tokens.css](../../../frontend/src/styles/tokens.css):
cream bg, white surfaces, 2px black strokes, hard shadows, pink `#FF3366` / teal `#00D4CC`,
Barlow Condensed numbers, Space Grotesk headings. No gradients, no soft shadows.

## Verification
- **Crawlers:** single-year rent smoke test parses a non-empty table; row counts sane vs sale.
- **Backend:** extend pytest suite in [backend/tests/](../../../backend/tests/) — migration applies,
  ETL loads rent/gold/min-wage, new endpoints return expected shapes (mirror existing test_api.py).
- **Frontend:** with backend + `npm run dev` running, use **Playwright MCP** to screenshot `/n/lozenets`
  full-page and at mobile width; verify the cluster renders, both charts draw, tables populate, and
  the slider recomputes values. Check the console for errors.

## Open risks
- Rent URL parse must be confirmed on a real fetch (smoke test gates the backfill).
- Free historical gold-price source must be located; fallback is a manually-curated CSV.
- Per-`property_type` rent may be sparser than sale in early years; table shows "—" when missing.
