# Sofia Building Registers — address→builder, builder→projects, under-construction

_Researched & validated 2026-07-20. Answers three product questions: (1) who built a given
address, (2) a developer's project portfolio, (3) all buildings under construction in Sofia._

## 0. TL;DR

The **НАГ София (Направление "Градско планиране и развитие")** publishes two live, searchable,
**exportable** registers that together answer all three questions. Backend is a Kendo-grid app on
`mapex.bg`; data goes back to **2006**. The **building-permit register alone is 84,390 records**,
each naming the **възложител (developer)**, the object, the district, the address + cadastral IDs,
and the effective date. **Validated live:** searching address "Христо Фотев" returned permit
**№127/26.09.2007, възложител КЕЙ ТИ ДЖИ БИЛДИНГ ГРУП ООД + Мария Петрова** — i.e. our existing
KTG entity (ЕИК 131232962), confirming from the official register a project we previously knew only
from the web.

## 1. The registers

| Register | URL | Contents |
|---|---|---|
| **Разрешение за строеж** (building permits) | https://nag.sofia.bg/RegisterBuildingPermitsPortal/Index | 84,390 permits. The "who + what + where + when-authorized" source. |
| **Удостоверение за въвеждане в експлоатация** (Акт 16 / put into operation) | https://nag.sofia.bg/RegisterCertificateForExploitationBuildings | Completion certificates. The "finished / duration" source. |

Both are searchable by **Адрес**, **Идентификатор КККР**, №, УПИ, Район, status, and date ranges,
with **xlsx + pdf export**. `възложител` = client-developer (not always the physical строител;
строителен надзор is listed separately).

## 2. Feature mapping

| Product question | How |
|---|---|
| **1. Who built address X + for how long** | Permit register by Адрес/КККР → `Employer`. Duration = permit effective date → Акт 16 date (cross-ref register 2). |
| **2. Builder → projects** (the layer missing from our network view) | Permit register by **възложител name/ЕИК** → full project list with dates + addresses. Join `Employer` string → our `Entity`/ЕИК. |
| **3. All buildings under construction in Sofia** | Permits with active status and **no matching Акт 16** = authorized/ongoing. ⚠ permit issued ≠ actually building; stalled ones (permit, no Акт 16, years elapsed) are themselves a **trust signal**. |

## 3. Scrape recipe (verified 2026-07-20)

Grid data comes from a POST returning clean JSON — **no HTML parsing needed**:

```
POST /RegisterBuildingPermitsPortal/Read
Content-Type: application/x-www-form-urlencoded; X-Requested-With: XMLHttpRequest
body: searchQueryId=<base-query-guid>&sort=&group=&filter=&page=<n>&pageSize=1000
→ { "Total": 84390, "Data": [ { ...row... } ] }
```

- **pageSize=1000 accepted; paging works** → whole register in **~85 requests**. (Or just hit the
  xlsx export once.)
- Row fields: `Number` ("127/26.09.2007"), `Hash`, `DocumentTypeName`, `Status`, `TakeEffect`
  (`/Date(epochMillis)/`), `Issuer`, **`Employer`** (възложител — companies in quotes + persons,
  comma-separated), `Object` (project description), `Region` (district), `Scope` (free-text blob:
  `Местност / Квартал / УПИ / Идентификатор КККР (имот) / Идентификатор КККР (сграда/СОС) / Адрес`).
- Detail page: `/RegisterInfo/Info?url=<Hash>` · Map: `/OpenMap/Zones?administrativeDocument=<Hash>`.
- ⚠ The **address/възложител filter is a server-side stored query** bound to `searchQueryId` +
  session (set by submitting the search form), *not* the Kendo `filter` param. For bulk work,
  **ignore filtering — pull the full base query once and filter/parse in our own DB.**
- `Scope` must be regex-parsed into structured fields (КККР имот `\d+\.\d+\.\d+`, КККР сграда, УПИ,
  Адрес). The КККР имот/сграда id is the **stable join key** to a physical building.

## 4. Coverage caveats

- **Pre-2015 rows are sparser/messier** — free-text addresses (e.g. "УЛ.ХРИСТО ФОТЕВ", no number),
  some missing effective dates. КTG's 2007 permit had address = just the street.
- For **older or missing** buildings, fall back to the **Имотен регистър** (property register):
  first-sale notary deeds name the developer as seller — the mechanism already used in
  `DEVELOPER_RESEARCH_PLAYBOOK.md`.
- **Cadastre (KAIS)** detailed reports now require a **КЕП e-signature** (since Aug 2025) → not a
  free bulk source; the free map view gives only identifier/area.

## 5. Build plan — "builder projects" feature

**Goal:** extend the network graph so each builder shows its **projects** (buildings), and support
address→builder lookup + an under-construction layer.

### 5.1 Data model (new)
```sql
CREATE TABLE building_permit (
  id SERIAL PRIMARY KEY,
  source_hash TEXT UNIQUE,              -- НАГ Hash (dedupe key)
  permit_number TEXT,                   -- "127/26.09.2007"
  doc_type TEXT,                        -- Разрешение за строеж / Акт 16
  status TEXT,
  effective_date DATE,
  issuer TEXT,
  employer_raw TEXT,                    -- verbatim възложител string
  object_desc TEXT,                     -- Строеж/Обект
  district TEXT,                        -- Region
  kkkr_imot TEXT, kkkr_sgrada TEXT,     -- parsed from Scope; join key to a building
  upi TEXT, mestnost TEXT, address TEXT,
  detail_url TEXT, scraped_at TIMESTAMP
);
CREATE TABLE permit_developer (        -- resolves employer_raw → our entities
  permit_id INT REFERENCES building_permit(id),
  entity_id INT REFERENCES entity(id),
  match_confidence TEXT,               -- 'eik' | 'name' | 'unmatched'
  PRIMARY KEY (permit_id, entity_id)
);
```
(Optionally a `building` table keyed on `kkkr_imot`/`kkkr_sgrada` to collapse multiple permits on
one physical building. Link `building`→`neighbourhood` for the map.)

### 5.2 Pipeline
1. **Scraper** `crawlers/scraper_kit/sites/nag_permits.py` — page the `/Read` endpoint (pageSize
   1000, ~85 reqs), write `data/raw/permits/sofia/nag_permits_<date>_<run-id>.jsonl`. Same for
   Акт 16 register. Idempotent on `source_hash`.
2. **Parser** — split `Scope` into structured fields; split `Employer` into company/person tokens.
3. **ETL** `etl.run_permits` — upsert `building_permit`; resolve `Employer` companies → `entity`
   via the **existing signals fuzzy-matcher** (ЕИК when derivable, else name; reuse
   `crawlers/signals/match.py`, same stopword/patronymic pitfalls). Unmatched employers become
   candidate new entities (feeds the developer-research pipeline).
4. **Under-construction view** = permits (жилищна/смесена сграда) with no Акт 16 on the same
   `kkkr_imot` and effective_date within ~N years.

### 5.3 API + UI
- `GET /api/entities/{eik}/projects` → permits for that developer (timeline).
- `GET /api/buildings?address=` / `?kkkr=` → address→builder lookup.
- `GET /api/map/under-construction` → active permits as map points.
- Frontend: a **Projects** section on the builder profile (list + timeline); reuse the Leaflet map
  for an under-construction layer. Keep DB data Cyrillic (per i18n rule — never `$t` register text).

### 5.4 Open decisions (resolve before coding)
- Scrape **all 84k** up front, or only жилищни/смесени сгради (skip ограда/преустройство noise)?
- Add a physical `building` table now, or attach permits directly to `entity` first and add the
  building layer later?
- Also scrape **Акт 16** in v1 (needed for accurate duration + under-construction), or permits-only
  MVP first?

## 6. Pointers
- Screenshot of the KTG validation: scratchpad `ktg_hristo_fotev_permit.png`
- Memory: `nag-sofia-permit-register.md` · Related: `DEVELOPER_RESEARCH_PLAYBOOK.md`
