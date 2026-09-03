# Spec — Browsable ownership graph, unified sidebar, and the neighbourhood bubble field

**Date:** 2026-05-31
**Branch:** `feat/neighbourhood-deep-dive`
**Status:** Approved design → ready for implementation plan

## Motivation

Three things, one cohesive piece of work:

1. **The ownership graph isn't browsable.** Search, profile, and ego-network are all keyed off the
   `Builder` table (134 КСБ-licensed companies only), but the graph holds **1251 entities**. A user
   searching "БИЛД ИНВЕСТ БЪЛГАРИЯ" (ЕИК 203539318 — a developer, not a licensed builder) gets
   nothing, even though it exists as a node. This is the documented OPEN GAP in
   `docs/PHASE35_HANDOVER.md`.
2. **Navigation is fragmented.** The home page has a sidebar; the builders pages each roll their own
   topbar with ad-hoc nav links. There is no single, always-visible navigation.
3. **The home "map" undersells the product.** A geographic Leaflet map shows what every other site
   shows. Replacing it with a **metric-driven bubble field** — one bubble per neighbourhood, size and
   colour encoding a *chosen* signal (price, buy-quality) — shows what others can't.

## Goals

- Search and open **any** entity (company, builder, or person), not just licensed builders.
- A single **persistent left sidebar** as the app's navigation, on every page.
- A **simple, list-first** browse page for entities, plus a per-entity page showing connections in
  both directions.
- Replace the home map with a **force-packed neighbourhood bubble field** driven by a metric selector
  (Price €/m², Buy signal/PtR for v1), with metric-aware colour and a live year slider.

## Non-goals (deferred)

- **Transport** and **Growth** metrics — data is partial (transport) or lower priority (growth). The
  metric system is built to extend, but these two are not in v1.
- Geographic positioning and the **metro-line overlay** are dropped with the map (the "Metro On/Off"
  toggle is removed — it has no meaning without a geo canvas).
- Depth-3 BFS, КСБ trust-signal scrapers, global-graph clustering (unchanged from prior backlog).

---

## A. Backend — entity-wide endpoints

New endpoints in `backend/app/routes.py`. The existing `/api/builders*` endpoints **stay** (no
breaking change); the frontend simply migrates to the entity ones.

### A1. `GET /api/entities`
Search across the `entity` table.

- **Query params:** `q` (name / ЕИК / person_key substring), `kind` (`company|person|builder`, optional),
  `limit` (default 50, ≤500), `offset`.
- **Per-row payload:** `id, eik, kind, name, is_builder, status, degree` where `degree` = count of
  edges incident on the entity (in + out). Computed with one grouped count query over `entity_edge`
  for the candidate ids (cheap at this scale).
- **Ordering:** builders first → `degree` desc → `name`.
- `kind=builder` filters `is_builder=true`; `kind=company` is companies incl. builders; `kind=person`
  is persons.

### A2. `GET /api/entities/{key}`
One entity's profile. `key` resolves in priority order: **ЕИК → person_key → numeric id**.

Generalises `get_builder` to any entity and returns connections **in both directions**:
- `owners` — incoming `ownership` edges (who owns this entity).
- `managers` — incoming `management` edges (who manages it).
- `owns` — **outgoing** `ownership` edges (companies this entity owns).
- `manages` — **outgoing** `management` edges (companies this person manages).
- If `is_builder`: also include `ksb_category`, `insolvency_flag`, `tax_debt_bgn`, `capital_bgn`,
  `address`, and linked `projects` (reuse the Builder lookup by ЕИК).

Helper `_outgoing_edges(session, entity_id, relation)` mirrors the existing `_incoming_edges`.

### A3. `GET /api/entities/{key}/network?depth=N`
Generalises `get_builder_network`: resolve the centre `Entity` by key (A2 resolver), then reuse the
existing `_ego_depths` / `_induced_edges` / `_node_dict` / `_edge_dict` machinery unchanged.

### A4. `GET /api/map` — add rent for PtR
Extend the per-neighbourhood payload to carry both overall €/m² values for the selected year:
```
{ slug, name, lat, lon, sale_eur_sqm, rent_eur_sqm }
```
- `sale_eur_sqm` is the current `value` (kept as an alias for back-compat during transition).
- `rent_eur_sqm` computed the same way as sale but with `transaction_type == "rent"`.
- PtR is **not** computed server-side — the frontend derives it (units cancel), so switching metric
  needs no refetch.

### Tests (`backend/tests/`, pytest, mirror `test_phase35_graph_api.py`)
- `GET /api/entities?q=БИЛД ИНВЕСТ` returns ЕИК **203539318** (the regression that started this).
- `GET /api/entities?q=<person name>` returns a person row with `kind=person`.
- `kind` filter narrows correctly; `degree` is present and > 0 for a connected node.
- `GET /api/entities/203539318` returns a profile with at least one of owners/managers/owns/manages.
- `GET /api/entities/{person_key}` resolves a person and lists the companies they own/manage.
- `GET /api/entities/203539318/network?depth=1` returns the centre + its direct neighbours.
- `GET /api/map` rows include `rent_eur_sqm` (null allowed where no rent data).

---

## B. Frontend — global sidebar shell

`App.vue` becomes a **shell**: a CSS grid with a persistent `Sidebar` (left) and the active view
(right). The view no longer imports its own sidebar.

```
<div class="shell">
  <Sidebar />               <!-- always visible -->
  <main class="shell__view"> <active view> </main>
</div>
```

**Sidebar contents (always visible):**
- Brand block.
- **Nav** (active-state from the current route):
  - `Карта` → `/` (bubble field)
  - `Строители и фирми` → `/entities` (entity browse)
- **Contextual rankings** — the existing "Top €/m²" list, but **metric-aware** (see C): title and
  values follow the active home metric ("Top €/m²" / "Best buys (PtR)"). Shown on the home route;
  hidden or replaced with a relevant summary on other routes.
- Export button (unchanged placeholder).

**Removed:** the `Metro On/Off` toggle (no geo canvas), the "Строители ↗" chip in `Navbar.vue`, and
the bespoke topbars in `BuildersView`/`BuilderView`. Page-specific controls (year slider, graph depth)
move into a **slim top strip** inside each view.

Active-route detection uses the existing `useRoute()` from `router.js`.

---

## C. Home — the neighbourhood bubble field

Replaces the Leaflet map. One bubble per neighbourhood, force-packed, **no geography**.

### C1. Shared component `BubbleCluster.vue`
Generalise the deep-dive's `NeighbourCluster` force-sim into one reusable component with two modes:
- **`directional`** — centre bubble + compass-anchored satellites (today's deep-dive ring; behaviour
  unchanged).
- **`pack`** — no centre; all bubbles pulled to canvas centre by a weak `forceX/forceY` + `forceCollide`,
  pre-settled then transitioned (same technique already in `NeighbourCluster`).

**Props:** `nodes` (`[{ slug, name, value, tone? }]`), `mode`, `valueFormat`, and an optional
`colorFn(node)`. Click a bubble → `navigate('/n/' + slug)`. Hover → highlight + show name/value.

`NeighbourhoodView` switches to `BubbleCluster` in `directional` mode. The old `NeighbourCluster.vue`
becomes unused — **flag for deletion, confirm with user before removing** (per repo guardrails).

### C2. Metric system
A metric selector (repurpose the stubbed chips in `Navbar.vue`) drives bubble **size** and **colour**.
Switching metric re-sizes with a transition and needs **no refetch** (all inputs already loaded).

| Metric key | Size input | Direction | Colour |
|------------|-----------|-----------|--------|
| `price` | `sale_eur_sqm` | bigger = pricier | single accent (pink) |
| `ptr` | `sale_eur_sqm / (rent_eur_sqm × 12)` | **inverted** (PtR 15 bigger than PtR 20) | metric-aware: `ptrVerdict` tone (green=buy … black=extreme) |

- PtR with no rent → `null` → smallest neutral bubble.
- Inverted sizing: clamp PtR to a sane band and map with a reversed range so lower PtR → larger radius.
- Colour for `ptr` reuses `ptrVerdict(ptr).tone` from `lib/finance.js`; add a `PTR_TONE_COLOR` map
  (buy/good/fair/stretched/expensive/overpriced/extreme/na → concrete Neo-Memphis hex) in `finance.js`
  so home and deep-dive share one source of truth.

### C3. State (`stores/appStore.js`)
- Add `metric` (default `'price'`) + `setMetric(key)`.
- `/api/map` now returns `sale_eur_sqm` + `rent_eur_sqm`; keep features carrying both.
- New getter `metricValue(feature)` and `ranked` becomes metric-aware (sorts by the active metric's
  size value; PtR sorts ascending = best buys first).
- Drop `metroOn` / `toggleMetro` (and the `metro` line data usage on the home canvas).

### C4. View (`MapView.vue` → bubble field)
- Renders the slim top strip (year slider + metric chips via `Navbar.vue`) and `BubbleCluster` in
  `pack` mode over the full canvas.
- Bubble nodes built from features: `{ slug, name, value: metricSize(f), tone: metricTone(f) }`.
- Loading/empty states preserved. Leaflet, `BubbleMap.vue`, and `data/metro` usage removed from this
  path (`BubbleMap.vue` left in tree, flagged for deletion pending confirmation).

---

## D. Entities browse + entity page

### D1. `EntitiesView.vue` (`/entities`) — list-first
- Stats strip (reuse, as in current `BuildersView`).
- Search box with type-ahead → `api.entities(q, kind)`.
- **Primary content = a results list** (not a graph): each row = name · kind badge
  (`builder`/`company`/`person`) · ЕИК or person id · status pill · connection count (`degree`).
  Click row → `navigate('/e/' + key)` (key = ЕИК for companies, person_key for persons).
- Kind filter: segmented `Всички / Строители / Фирми / Хора`.
- The global constellation graph moves behind a **"Мрежа" (Network) toggle**, so the default is the
  simple list the user asked for.

### D2. `EntityView.vue` (`/e/{key}`) — generalises `BuilderView`
- Left profile panel: name, kind badge, ЕИК/person id, status; for companies also capital + address;
  for builders also КСБ pills + projects.
- **Four connection sections**: `Собственици` (owners), `Управители` (managers),
  `Притежава` (owns — outgoing ownership), `Управлява` (manages — outgoing management). Each lists
  name + share %/role + current/бивш, with a dot colour by kind, click → that entity's page.
- Right: depth-controlled ego graph (`OwnershipGraph`) via `api.entityNetwork(key, depth)`.
- `BuilderView.vue` is replaced by `EntityView.vue` (builder = entity with `is_builder`).

---

## E. Routing & API client

### `router.js`
- `/` → `map` (bubble field) — unchanged path.
- `/n/{slug}` → neighbourhood — unchanged.
- `/entities` → `entities` (new).
- `/e/{key}` → `entity` (new).
- **Aliases:** `/builders` → `entities`; `/b/{eik}` → `entity` with `key=eik` (keep old links working).

### `App.vue`
Route → view map updated: `map → MapView`, `entities → EntitiesView`, `entity → EntityView`,
`neighbourhood → NeighbourhoodView`. Sidebar rendered once in the shell, outside the switch.

### `api/index.js`
- `entities: (q, kind) => get('/entities?...')`
- `entity: (key) => get('/entities/' + key)`
- `entityNetwork: (key, depth=2) => get('/entities/' + key + '/network?depth=' + depth)`
- `map` updated consumers to read `sale_eur_sqm`/`rent_eur_sqm`.
- Old `builders`/`builder`/`builderNetwork` kept until callers are migrated, then removed.

---

## F. Verification

- **Backend:** new pytest cases above, run `cd backend && .venv/bin/python -m pytest -q` (must keep the
  46 existing green + add the new ones).
- **Frontend:** no test harness exists. Verify end-to-end with the already-configured Playwright MCP on
  `./dev.sh`:
  1. Home renders the bubble field; toggling Price ↔ Buy signal re-sizes + recolours bubbles; year
     slider rearranges them; clicking a bubble opens the deep-dive.
  2. Sidebar is present and identical on every route; nav highlights the active page.
  3. Search "БИЛД ИНВЕСТ" → result appears → open it → its connections render (the original bug, fixed).
  4. Open a person from a company's connection list → their owned/managed companies render.

## Risks / tradeoffs

- **Map removal** drops geography + metro overlay. Accepted by the user; the bubble field is the
  intended differentiator. Old `BubbleMap.vue` + `data/metro` retained in-tree (not deleted) until
  confirmed, in case we later want a geo toggle.
- **`NeighbourCluster.vue` → `BubbleCluster.vue`** leaves the old file orphaned; deletion gated on user
  confirmation.
- **Entity key collisions** (eik vs id) avoided by the fixed resolver order (eik → person_key → id);
  person_keys are non-numeric hashes so they never collide with numeric eiks/ids.

## File-by-file change list

**Backend**
- `app/routes.py` — add `/api/entities`, `/api/entities/{key}`, `/api/entities/{key}/network`,
  `_outgoing_edges` helper, entity-key resolver; extend `/api/map` with `rent_eur_sqm`.
- `tests/test_phase35_entities_api.py` (new) — endpoint + regression tests.

**Frontend**
- `App.vue` — shell with persistent sidebar + route switch.
- `components/Sidebar.vue` — real nav (Карта / Строители и фирми), metric-aware rankings, metro removed.
- `components/Navbar.vue` — chips become the real metric selector (Price / Buy signal).
- `components/BubbleCluster.vue` (new) — shared force-bubble, `directional` + `pack` modes.
- `views/MapView.vue` — bubble field (replaces Leaflet).
- `views/NeighbourhoodView.vue` — use `BubbleCluster` (directional).
- `views/EntitiesView.vue` (new, replaces/renames `BuildersView.vue`) — list-first browse.
- `views/EntityView.vue` (new, replaces `BuilderView.vue`) — bidirectional connections + ego graph.
- `stores/appStore.js` — `metric` state, metric-aware getters, rent in features, metro removed.
- `router.js` — `/entities`, `/e/{key}`, aliases for `/builders` and `/b/{eik}`.
- `api/index.js` — `entities`, `entity`, `entityNetwork`; `map` payload update.
- `lib/finance.js` — `PTR_TONE_COLOR` map.
- **Pending deletion (confirm first):** `components/NeighbourCluster.vue`, `components/BubbleMap.vue`,
  `views/BuildersView.vue`, `views/BuilderView.vue`, `data/metro.js`.
