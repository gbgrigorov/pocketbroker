# Official-records Check — Implementation Plan (FINALIZED 2026-06-02)

> **Status: closed — both components landed.** Component A pivoted hard during execution
> (see Outcome). Component B (insolvency status) is now **implemented** (Tasks 9–11, 63
> backend tests green; ETL derives flags for all 135 builders — 0 currently insolvent).
> All committed on `feat/new-building-projects`. The legalacts auto-ingest remains the
> only deliberately-dropped item.

**Original goal:** populate the **official** evidence tier with real court records for
АРТЕКС, and auto-derive builder insolvency status from Papagal.

---

## Outcome (what actually happened)

Execution turned the original "scrape court acts" goal into a much better result once the
live site and the real data were inspected.

### Component A — court records: PIVOTED, not as designed
The planned legalacts CAPTCHA-assistant was **dropped for auto-ingestion**. Recon proved it
unworkable and the investigation found a better truth:
- legalacts search is **image-CAPTCHA gated**; results are **anonymised** (no party/ЕИК);
  act bodies are PDFs behind a **"Моля, изчакайте!" JavaScript anti-bot interstitial**;
  full-text name search is **noisy** (~2/3 false positives, incl. a different "Артекс
  инженеринг 2000 ООД"). We do not defeat CAPTCHAs/JS challenges.
- **Key learning (saved to memory `court-cases-hide-in-spvs`):** developers litigate
  through **per-project SPVs**. The Златен век saga is under **„Артекс Златен век" ООД,
  ЕИК `175376051`** — *not* the parent „Артекс Инженеринг" АД (`175155346`). They share
  owner **Елена Иванова** (and Иван Иванов father/son split across the two).

**What shipped instead (committed):**
1. **Modelled the real entity + group.** Pulled the SPV + parent + a depth-2 owner
   expansion via the existing Papagal scraper → the full **97-company Артекс
   constellation** is in the ownership graph, all linked through the Иванови.
2. **Curated 4 official-tier records** on the SPV (`data/raw/signals/sofia/registry_zlaten_vek_2026-06-02.jsonl`):
   ДНСК stop-order 15.04.2019; chief-architect design dispute; ВАС 14.07.2022 (permit
   № 134/26.01.2007 valid, чл.128 ал.2 АПК); ДНСК actions annulled. Neutral framing, real
   source links → `etl.run_signals` → `tier="official"` on entity `175376051`.
3. **Conservative cross-entity propagation** (`backend/app/routes.py`): a **builder's**
   profile now aggregates **official-tier** signals from co-owned sibling SPVs, labelled
   *"via собственик X → Артекс Златен век ООД"*. Forum/web never bubble up; list view
   unchanged. So Артекс Инженеринг АД's page now shows the Златен век court record
   (official: 4). Tested (`backend/tests/test_signal_propagation.py`), 61 backend tests green.

**Retained but shelved (committed, not wired into ingestion):** `crawlers/signals/official.py`
(pure helpers), `crawlers/scraper_kit/sites/legalacts.py` (search + `parse_results`, human
CAPTCHA capture only), with unittests. Useful for ad-hoc human-driven verification; the
legalacts results fixture is local-only (fixtures/ gitignored, as for papagal).

### Component B — insolvency status: NOT STARTED (deferred)
Clean and unblocked. Tasks 9–11 below are ready to execute as-is.

### Per-task disposition
| Plan task | Disposition |
|---|---|
| 1 pure helpers (`official.py`) | ✅ committed |
| 2 shortlist file | ✅ committed |
| 3 legalacts skeleton (search+CAPTCHA) | ✅ committed (shelved tool) |
| 4 capture fixture (human CAPTCHA) | ✅ done (revealed the blockers) |
| 5 `parse_results` (lean) | ✅ committed |
| 6 body-fetch + ЕИК-confirm | ❌ dropped (JS-gated bodies, anonymised, noisy) |
| 7 route `legalacts_*.jsonl` → load_registry | ❌ not needed (curated file is `registry_*.jsonl`, already globbed) |
| 8 end-to-end Артекс run | ↪️ replaced by SPV modelling + curation + propagation |
| 9 `insolvency_from_status` | ✅ committed |
| 10 `derive_insolvency_flags` ETL | ✅ committed |
| 11 wire into `run_phase35` | ✅ committed (135 builders flagged, 0 insolvent) |

### Commits (this work, on `feat/new-building-projects`)
`docs: design`, `docs: plan`, `feat(signals): pure helpers`, `chore: shortlist`,
`feat(signals): legalacts skeleton`, `feat(signals): parse legalacts results`,
`feat(signals): surface sibling-SPV official records on a builder's page`.
(Raw crawl data + curated registry jsonl are local — `data/raw/ownership` gitignored.)

### Out of scope (confirmed)
legalacts auto-ingestion; generic all-companies court scraper; NAP tax-debt; BRRA TR-API;
ДНСК/ВАС primary-source scrapers. CAPTCHA/JS-challenge solving — never.

---

## DEFERRED — Component B: automatic insolvency status (ready to execute)

Derive `Builder.insolvency_flag` from the `Статус` Papagal already scrapes. CAPTCHA-free,
all builders. Pure-function TDD + a small ETL step.

### Task 9: Pure `insolvency_from_status`

**Files:** Modify `crawlers/scraper_kit/sites/papagal.py`; Modify `crawlers/scraper_kit/tests/test_papagal.py`

- [ ] **Step 1 — failing test** (append to `test_papagal.py`):

```python
from crawlers.scraper_kit.sites.papagal import insolvency_from_status


class InsolvencyFromStatusTest(unittest.TestCase):
    def test_active_is_false(self):
        self.assertFalse(insolvency_from_status("Активен"))

    def test_none_is_false(self):
        self.assertFalse(insolvency_from_status(None))

    def test_insolvency_true(self):
        self.assertTrue(insolvency_from_status("В несъстоятелност"))

    def test_liquidation_true(self):
        self.assertTrue(insolvency_from_status("В ликвидация"))

    def test_deleted_true(self):
        self.assertTrue(insolvency_from_status("Заличен"))
```

- [ ] **Step 2 — run, expect fail:** `python3 -m unittest crawlers.scraper_kit.tests.test_papagal -v` → `cannot import name 'insolvency_from_status'`

- [ ] **Step 3 — implement** (in `papagal.py`, after `_clean`):

```python
# Status phrases (lowercased substring match) that indicate a distressed company.
_DISTRESS_STATUS = ("несъстоятел", "ликвидаци", "заличен")


def insolvency_from_status(status: Optional[str]) -> bool:
    """True if a Papagal ``Статус`` string indicates insolvency/liquidation/erasure."""
    if not status:
        return False
    low = status.lower()
    return any(token in low for token in _DISTRESS_STATUS)
```

- [ ] **Step 4 — run, expect pass:** same command, existing + 5 new green.
- [ ] **Step 5 — commit:** `git add crawlers/scraper_kit/sites/papagal.py crawlers/scraper_kit/tests/test_papagal.py && git commit`

### Task 10: ETL derivation `derive_insolvency_flags`

**Files:** Modify `backend/etl/entities.py`; Create `backend/tests/test_insolvency_derive.py`

- [ ] **Step 1 — failing test:**

```python
# backend/tests/test_insolvency_derive.py
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Builder, Entity
from etl.entities import derive_insolvency_flags


@pytest.fixture
def session():
    engine = create_engine("sqlite://", future=True,
                          connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, future=True)()
    yield s
    s.close()


def test_derives_flag_from_status(session):
    e = Entity(kind="company", eik="111", name="X", is_builder=True, status="В несъстоятелност")
    session.add(e); session.flush()
    session.add(Builder(eik="111", name="X", entity_id=e.id)); session.commit()
    assert derive_insolvency_flags(session) == 1
    session.commit()
    assert session.scalar(select(Builder).where(Builder.eik == "111")).insolvency_flag is True


def test_active_builder_not_flagged(session):
    e = Entity(kind="company", eik="222", name="Y", is_builder=True, status="Активен")
    session.add(e); session.flush()
    session.add(Builder(eik="222", name="Y", entity_id=e.id)); session.commit()
    derive_insolvency_flags(session); session.commit()
    assert session.scalar(select(Builder).where(Builder.eik == "222")).insolvency_flag is False
```

- [ ] **Step 2 — run, expect fail:** `cd backend && .venv/bin/pytest tests/test_insolvency_derive.py -q` → `cannot import name 'derive_insolvency_flags'`

- [ ] **Step 3 — implement** (in `backend/etl/entities.py`):

```python
def derive_insolvency_flags(session) -> int:
    """Set ``Builder.insolvency_flag`` from the backing entity's Papagal status.

    Idempotent; returns the number of builders whose flag changed.
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from crawlers.scraper_kit.sites.papagal import insolvency_from_status

    updated = 0
    rows = session.execute(
        select(Builder, Entity).join(Entity, Entity.id == Builder.entity_id)
    ).all()
    for builder, entity in rows:
        flag = insolvency_from_status(entity.status)
        if bool(builder.insolvency_flag) != flag:
            builder.insolvency_flag = flag
            updated += 1
    session.flush()
    return updated
```

- [ ] **Step 4 — run, expect pass.**
- [ ] **Step 5 — commit.**

### Task 11: Wire into the phase-3.5 ETL

**Files:** Modify `backend/etl/run_phase35.py`

- [ ] **Step 1 — import + call** before `session.commit()` in `main()`:

```python
from etl.entities import OwnershipReport, load_ownership, derive_insolvency_flags
# ...
        flagged = derive_insolvency_flags(session)
        print(f"insolvency flags derived/updated: {flagged}")
```

- [ ] **Step 2 — suite green:** `cd backend && .venv/bin/pytest -q`
- [ ] **Step 3 — run ETL:** `cd backend && .venv/bin/python -m etl.run_phase35` → prints `insolvency flags derived/updated: <n>`
- [ ] **Step 4 — commit.**

---

## References
- Spec: `docs/superpowers/specs/2026-06-02-official-records-check-design.md`
- Memories: `court-cases-hide-in-spvs`, `official-records-check-findings`
