# Rent + EUR-only Data Foundation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collect imot.bg **rent** data (current + 30-year history) into the same pipeline as sale data, add a `transaction_type` discriminator to `price_snapshot`, and drop the redundant BGN columns (EUR-only).

**Architecture:** Rent reuses the existing sale pipeline end-to-end. The two existing crawlers are parametrized to fetch the `naemi-` (rentals) URL and tag rows `transaction_type: "rent"`; rows flow through the existing ETL unchanged except for one new field and the removal of the two derived BGN columns. One Alembic migration covers the schema change.

**Tech Stack:** Python 3 · httpx · BeautifulSoup · SQLAlchemy 2.0 · Alembic · pytest · PostgreSQL 16.

**Source spec:** [docs/superpowers/specs/2026-05-30-neighbourhood-deep-dive-page-design.md](../specs/2026-05-30-neighbourhood-deep-dive-page-design.md) (Parts A1, B1, B3).

> **Network note (user guardrail):** Running the crawlers hits imot.bg over the network. Per the
> project's safety rules, **ask the user before running any crawler/network command.** Crawler tasks
> below are verified by a smoke run (live fetch) rather than mocked unit tests, matching the repo's
> existing convention (crawlers have no unit tests; ETL/API do).

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| [crawlers/imot_prices.py](../../../crawlers/imot_prices.py) | Modify | Current snapshot: add sale/rent mode + generalized slug regex |
| [crawlers/imot_bg_history.py](../../../crawlers/imot_bg_history.py) | Modify | History: add sale/rent mode (swap URL) |
| [backend/app/models.py](../../../backend/app/models.py) | Modify | `PriceSnapshot`: +`transaction_type`, −`price_bgn`/`price_bgn_sqm` |
| `backend/alembic/versions/<rev>_rent_txn_eur_only.py` | Create | Migration: add column + index, drop BGN columns |
| [backend/etl/load.py](../../../backend/etl/load.py) | Modify | Loader: set `transaction_type`, drop BGN fields |
| [backend/etl/build_registry.py](../../../backend/etl/build_registry.py) | Modify | Add rent file glob constants |
| [backend/etl/run_etl.py](../../../backend/etl/run_etl.py) | Modify | Merge rent records into the load; extend conservation report |
| [backend/tests/test_load.py](../../../backend/tests/test_load.py) | Modify | Cover `transaction_type` + EUR-only |

---

## Task 1: Current crawler — sale/rent mode + generalized slug regex

**Files:**
- Modify: `crawlers/imot_prices.py`

- [ ] **Step 1: Generalize the slug regex** so it matches both `prodazhbi-` (sale) and `naemi-` (rent) hrefs.

In [crawlers/imot_prices.py:163](../../../crawlers/imot_prices.py#L163), change:
```python
    match = re.search(r"/prodazhbi-([^/]+)/([^?\"#]+)", href)
```
to:
```python
    match = re.search(r"/(?:prodazhbi|naemi)-([^/]+)/([^?\"#]+)", href)
```

- [ ] **Step 2: Parametrize the fetch with a transaction type.**

Change the signature and URL selection of `fetch_main_table` ([line 187](../../../crawlers/imot_prices.py#L187)):
```python
async def fetch_main_table(client: httpx.AsyncClient, transaction_type: str = "sale") -> list[dict]:
    """Fetch the sredni-ceni table for sales ('sale') or rentals ('rent')."""
    url = SREDNI_CENI_URL if transaction_type == "sale" else f"{BASE_URL}/sredni-ceni/naemi-sofiya"
    log.info("Fetching %s (%s)", url, transaction_type)
```
Then replace the two `resp = await client.get(SREDNI_CENI_URL)` / log line usages in that function with `url`, and in the record dict ([line 268](../../../crawlers/imot_prices.py#L268)) set:
```python
                "transaction_type": transaction_type,
```

- [ ] **Step 3: Add a CLI flag** so the script can be run for either type.

Replace `main()` ([line 338](../../../crawlers/imot_prices.py#L338)) body's client block to pass the type, and add argparse:
```python
import argparse  # add near the other imports at top

async def main(transaction_type: str = "sale"):
    log.info("Starting imot.bg price scraper (%s)", transaction_type)
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=30.0) as client:
        records = await fetch_main_table(client, transaction_type)
    if not records:
        log.error("No records scraped — check errors above")
        sys.exit(1)
    for record in records:
        print(json.dumps(record, ensure_ascii=False))
    log.info("Done. %d records printed.", len(records))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="imot.bg current sredni-ceni scraper")
    parser.add_argument("--transaction-type", choices=["sale", "rent"], default="sale")
    args = parser.parse_args()
    asyncio.run(main(args.transaction_type))
```

- [ ] **Step 4: Smoke test (network — ASK USER FIRST).**

Run:
```bash
python3 crawlers/imot_prices.py --transaction-type rent 2>/dev/null | head -3
```
Expected: JSON lines where `"transaction_type": "rent"`, `"neighborhood_slug"` is non-null (e.g. `"lozenets"`), and `price_eur`/`price_eur_sqm` are populated. If the table is empty or slugs are null, STOP — the rent URL/markup differs and Task 1 needs revisiting before proceeding.

- [ ] **Step 5: Generate the current rent snapshot file.**

Run:
```bash
python3 crawlers/imot_prices.py --transaction-type rent \
  > data/raw/imot_bg/sofia_current_rent_$(date +%Y-%m).jsonl
wc -l data/raw/imot_bg/sofia_current_rent_*.jsonl
```
Expected: a few hundred rows.

- [ ] **Step 6: Commit.**
```bash
git add crawlers/imot_prices.py data/raw/imot_bg/sofia_current_rent_*.jsonl
git commit -m "feat(crawler): add rent mode to current imot.bg scraper"
```

---

## Task 2: History crawler — sale/rent mode

**Files:**
- Modify: `crawlers/imot_bg_history.py`

- [ ] **Step 1: Make the base URL depend on transaction type.**

In [crawlers/imot_bg_history.py:37](../../../crawlers/imot_bg_history.py#L37), keep `BASE_URL` and replace the constant `HISTORY_URL` with a helper:
```python
def history_url(transaction_type: str = "sale") -> str:
    section = "naemi-sofiya" if transaction_type == "rent" else "prodazhbi-sofiya"
    return f"{BASE_URL}/sredni-ceni/{section}"
```

- [ ] **Step 2: Thread `transaction_type` through the fetch + record functions.**

`fetch_dates_for_year` and `fetch_snapshot` take a `transaction_type` arg and use `history_url(transaction_type)` instead of the old constant:
```python
async def fetch_dates_for_year(client, year: int, transaction_type: str = "sale") -> list[str]:
    resp = await client.get(history_url(transaction_type), params={"year": str(year)}, timeout=30)
    ...

async def fetch_snapshot(client, year: int, date_str: str, transaction_type: str = "sale") -> list[dict]:
    resp = await client.get(history_url(transaction_type), params={"year": str(year), "date": date_str}, timeout=30)
    ...
```
In the record dict ([line 227](../../../crawlers/imot_bg_history.py#L227)) add:
```python
                "transaction_type": transaction_type,
```

- [ ] **Step 3: Add the CLI flag and thread it through `run`/`main`.**

In `run(...)` add a `transaction_type` parameter and pass it to both fetch calls. In `main()` add:
```python
    parser.add_argument("--transaction-type", choices=["sale", "rent"], default="sale")
```
and pass `args.transaction_type` into `run(...)`. Default `--output-dir` for rent should be `data/raw/imot_bg/sofia_history_rent` (caller supplies it; see Step 5).

- [ ] **Step 4: Smoke test one year (network — ASK USER FIRST).**

Run:
```bash
python3 crawlers/imot_bg_history.py --transaction-type rent --start-year 1995 --end-year 1995 2>&1 | head -5
```
Expected: stderr shows a chosen date near 15.10.1995 and ">0 records"; stdout JSON lines carry `"transaction_type": "rent"`. If 0 records, STOP and inspect the rent history markup.

- [ ] **Step 5: Backfill full rent history (network — ASK USER FIRST; ~35 min).**
```bash
python3 crawlers/imot_bg_history.py --transaction-type rent \
  --output-dir data/raw/imot_bg/sofia_history_rent
ls data/raw/imot_bg/sofia_history_rent/ | wc -l   # expect ~31 files
```

- [ ] **Step 6: Commit.**
```bash
git add crawlers/imot_bg_history.py data/raw/imot_bg/sofia_history_rent/
git commit -m "feat(crawler): add rent mode to historical imot.bg scraper"
```

---

## Task 3: Model — add `transaction_type`, drop BGN columns

**Files:**
- Modify: `backend/app/models.py:45-60`

- [ ] **Step 1: Edit the `PriceSnapshot` model.**

In [backend/app/models.py](../../../backend/app/models.py#L45), **remove** these two lines:
```python
    price_bgn: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    price_bgn_sqm: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
```
and **add** (after `property_type`):
```python
    transaction_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 'sale' | 'rent'
```

- [ ] **Step 2: Commit.**
```bash
git add backend/app/models.py
git commit -m "refactor(model): price_snapshot transaction_type + drop BGN columns"
```

---

## Task 4: Alembic migration

**Files:**
- Create: `backend/alembic/versions/<rev>_rent_txn_eur_only.py`

- [ ] **Step 1: Generate an empty revision.**
```bash
cd backend && .venv/bin/alembic revision -m "rent txn type and eur only"
```
Expected: a new file under `backend/alembic/versions/` with `down_revision = '2575703c0c0e'`.

- [ ] **Step 2: Fill in `upgrade()` / `downgrade()`.**
```python
def upgrade() -> None:
    op.add_column('price_snapshot', sa.Column('transaction_type', sa.Text(), nullable=True))
    op.execute("UPDATE price_snapshot SET transaction_type = 'sale' WHERE transaction_type IS NULL")
    op.create_index('ix_price_snapshot_nbhd_txn_period', 'price_snapshot',
                    ['neighbourhood_id', 'transaction_type', 'period_date'])
    op.drop_column('price_snapshot', 'price_bgn')
    op.drop_column('price_snapshot', 'price_bgn_sqm')


def downgrade() -> None:
    op.add_column('price_snapshot', sa.Column('price_bgn_sqm', sa.Numeric(), nullable=True))
    op.add_column('price_snapshot', sa.Column('price_bgn', sa.Numeric(), nullable=True))
    op.drop_index('ix_price_snapshot_nbhd_txn_period', table_name='price_snapshot')
    op.drop_column('price_snapshot', 'transaction_type')
```

- [ ] **Step 3: Apply and verify round-trip.**
```bash
cd backend && .venv/bin/alembic upgrade head && .venv/bin/alembic downgrade -1 && .venv/bin/alembic upgrade head
```
Expected: all three succeed with no error.

- [ ] **Step 4: Commit.**
```bash
git add backend/alembic/versions/
git commit -m "feat(db): migration for transaction_type + EUR-only price_snapshot"
```

---

## Task 5: ETL loader — set `transaction_type`, drop BGN fields (TDD)

**Files:**
- Modify: `backend/etl/load.py:19-53`
- Test: `backend/tests/test_load.py`

- [ ] **Step 1: Write failing tests.**

Add to [backend/tests/test_load.py](../../../backend/tests/test_load.py): extend the `current_records` fixture's first row with `"transaction_type": "rent"` (leave others without the key), then add:
```python
def test_transaction_type_defaults_to_sale_and_respects_rent(session, fixtures):
    registry, current, history, resolver = fixtures
    load_all(session, registry=registry, current_records=current,
             history_records=history, resolver=resolver)
    rows = session.scalars(select(PriceSnapshot)).all()
    kinds = sorted({r.transaction_type for r in rows})
    assert kinds == ["rent", "sale"]              # rent row tagged, others default to 'sale'

def test_model_has_no_bgn_columns():
    assert not hasattr(PriceSnapshot, "price_bgn")
    assert not hasattr(PriceSnapshot, "price_bgn_sqm")
```
(Add `from app.models import PriceSnapshot` and `select` import if not present — both already imported.)

- [ ] **Step 2: Run, verify failure.**
```bash
cd backend && .venv/bin/pytest tests/test_load.py -k "transaction_type or bgn" -v
```
Expected: FAIL (`transaction_type` attribute missing / still has bgn).

- [ ] **Step 3: Implement.**

In [backend/etl/load.py:19](../../../backend/etl/load.py#L19) change `_PRICE_FIELDS` to drop BGN:
```python
_PRICE_FIELDS = ("price_eur", "price_eur_sqm", "overall_avg_eur_sqm")
```
In `_price_snapshot` ([line 45](../../../backend/etl/load.py#L45)) add the field:
```python
        transaction_type=rec.get("transaction_type", "sale"),
```

- [ ] **Step 4: Run, verify pass (whole file, to catch regressions).**
```bash
cd backend && .venv/bin/pytest tests/test_load.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit.**
```bash
git add backend/etl/load.py backend/tests/test_load.py
git commit -m "feat(etl): load transaction_type, drop BGN fields"
```

---

## Task 6: Wire rent files into the ETL run

**Files:**
- Modify: `backend/etl/build_registry.py:21-23`
- Modify: `backend/etl/run_etl.py`

- [ ] **Step 1: Add rent glob constants.**

In [backend/etl/build_registry.py](../../../backend/etl/build_registry.py#L21), after the existing `CURRENT` / `HISTORY_GLOB`:
```python
CURRENT_RENT_GLOB = os.path.join(REPO_ROOT, "data/raw/imot_bg/sofia_current_rent_*.jsonl")
HISTORY_RENT_GLOB = os.path.join(REPO_ROOT, "data/raw/imot_bg/sofia_history_rent/*.jsonl")
```

- [ ] **Step 2: Merge rent records into the load.**

In [backend/etl/run_etl.py](../../../backend/etl/run_etl.py), import the new globs and append rent rows to the existing lists (registry is still built from SALE current only):
```python
from etl.build_registry import (COORDS, CURRENT, HISTORY_GLOB, CURRENT_RENT_GLOB,
                                 HISTORY_RENT_GLOB, load_jsonl)
...
current_records = list(load_jsonl(CURRENT))
for p in sorted(glob.glob(CURRENT_RENT_GLOB)):
    current_records += list(load_jsonl(p))
history_records = [r for p in sorted(glob.glob(HISTORY_GLOB)) for r in load_jsonl(p)]
for p in sorted(glob.glob(HISTORY_RENT_GLOB)):
    history_records += list(load_jsonl(p))
```
The conservation assertions already use `len(current_records)` / `len(history_records)`, so they stay correct with rent included.

- [ ] **Step 3: Commit.**
```bash
git add backend/etl/build_registry.py backend/etl/run_etl.py
git commit -m "feat(etl): include rent snapshots in the load"
```

---

## Task 7: Full reload + end-to-end verification

**Files:** none (operational).

- [ ] **Step 1: Reload the database (assumes Postgres running, rent files present).**
```bash
cd backend && .venv/bin/python -m etl.run_etl --reset
```
Expected report: `current` and `history` loaded counts now exceed the sale-only baseline (sale + rent), conservation line prints "every input row accounted for".

- [ ] **Step 2: Verify rent rows landed (EUR-only, both types).**
```bash
cd backend && .venv/bin/python -c "
from app.db import SessionLocal; from app.models import PriceSnapshot
from sqlalchemy import select, func
s=SessionLocal()
print('by type:', dict(s.execute(select(PriceSnapshot.transaction_type, func.count()).group_by(PriceSnapshot.transaction_type)).all()))
"
```
Expected: both `'sale'` and `'rent'` present with non-trivial counts.

- [ ] **Step 3: Run the full backend test suite.**
```bash
cd backend && .venv/bin/pytest -q
```
Expected: all pass (22 prior + new).

- [ ] **Step 4: Commit any seed/report changes if produced.**
```bash
git add -A && git commit -m "chore(etl): full reload with rent data" || echo "nothing to commit"
```

---

## Self-Review

- **Spec coverage (A1, B1, B3):** rent current crawler (T1), rent history crawler (T2), `transaction_type` column + index + BGN drop (T3/T4), loader changes (T5), run wiring (T6), reload (T7). ✅
- **Placeholder scan:** all steps contain concrete code/commands. The only conditional is the gold/min-wage work, which is intentionally split into Plan 1b. ✅
- **Type consistency:** `transaction_type` (str, `'sale'`/`'rent'`) used identically in crawlers, model, loader, and tests; index name `ix_price_snapshot_nbhd_txn_period` matches between up/downgrade. ✅
- **Risk:** rent URL/markup is verified by the Task 1/2 smoke tests *before* any bulk crawl — the plan halts if imot.bg's rent pages differ from sales.
