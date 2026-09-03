# Research Sync API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the MacBook an HTTP API to read new research requests off production and push findings straight into the production database as one atomic, idempotent bundle.

**Architecture:** A new `backend/app/sync/` package — Pydantic bundle schemas, a FastAPI-free upsert engine, and a thin router mounted at `/api/admin/sync`, gated by a dedicated token and unreachable from the public internet (nginx `deny all` + SSH tunnel). The natural-key upsert helpers that already exist in `backend/etl/entities.py` move up into `backend/app/` so the API and the ETL share one implementation. A stdlib-only `scripts/pb.py` drives it from the Mac.

**Tech Stack:** Python 3, FastAPI, SQLAlchemy 2.0 (`Mapped`/`mapped_column`), Alembic, Pydantic v2, pytest + `TestClient` over in-memory SQLite.

Spec: [`docs/superpowers/specs/2026-08-20-research-sync-api-design.md`](../specs/2026-08-20-research-sync-api-design.md)

## Global Constraints

- **No new dependencies.** Not on the MacBook, not on the VPS. `scripts/pb.py` is standard library only (`urllib`, `json`, `subprocess`, `argparse`).
- **No sync code path may read or write `user` or `oauth_account`.** Asserted in tests.
- **Auth fails closed:** when `RESEARCH_API_TOKEN` is unset, every sync endpoint returns 403.
- **Enrich, don't erase:** a `null` or omitted bundle field never overwrites a non-null production value.
- **Dry run is the default** on every write endpoint (`dry_run=True`).
- **Entities are referenced by natural key only** (`eik` / `person_key`) — local database ids never cross the wire.
- **Capital crosses the wire as `capital_eur`** and is converted at `BGN_PER_EUR = 1.95583` by the shared helper. The column is `capital_bgn`.
- Tests run from `backend/`: `.venv/bin/python -m pytest`.
- Column type for `sync_log.summary` is `sa.JSON` (not JSONB) so the SQLite test suite can exercise it.
- Commit messages end with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- **Never `git push`** — the human pushes.

---

### Task 1: Move the shared upsert helpers into `app/`

Pure refactor, zero behaviour change. The API must not import from `etl`, so the natural-key helpers move up. `etl/entities.py` re-exports them, keeping every existing ETL caller working.

**Files:**
- Create: `backend/app/names.py`
- Create: `backend/app/entities.py`
- Modify: `backend/etl/entities.py` (delete moved bodies, re-export)
- Modify: `backend/etl/load_phase3.py:49-56` (delete `_norm_name` body, import it)
- Test: `backend/tests/test_app_entities.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `app.names.norm_name(name: Optional[str]) -> str`
  - `app.entities.BGN_PER_EUR: float`
  - `app.entities.entity_for_company(session, eik: str, *, name=None, legal_form=None, status=None, address=None, capital_eur=None, founded_year=None, source=None) -> Tuple[Entity, bool]`
  - `app.entities.entity_for_person(session, name: str, person_key: Optional[str], *, source=None) -> Tuple[Entity, bool]`
  - `app.entities.entity_for_builder(session, builder: Builder) -> Entity`
  - `app.entities.upsert_edge(session, src_entity_id: int, dst_entity_id: int, relation: str, *, share_pct=None, role=None, valid_from=None, valid_to=None, is_current=True, source=None) -> EntityEdge`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_app_entities.py`:

```python
"""The natural-key entity helpers live in app/ so the API can use them without
importing the ETL package. This test pins the new import path and the
enrich-don't-erase contract the sync layer depends on."""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.entities import entity_for_company, entity_for_person, upsert_edge
from app.models import Entity
from app.names import norm_name


@pytest.fixture
def session():
    engine = create_engine("sqlite://", future=True,
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, future=True)()
    yield s
    s.close()


def test_norm_name_strips_legal_form_and_quotes():
    assert norm_name('„АРТЕКС ИНЖЕНЕРИНГ" АД') == "артекс инженеринг"
    assert norm_name(None) == ""


def test_company_upserts_on_eik_and_enriches(session):
    a, created = entity_for_company(session, "175376051", name="Артекс Златен век ООД")
    assert created is True
    b, created = entity_for_company(session, "175376051", founded_year=2008)
    assert created is False and b.id == a.id
    # the second call added a field without erasing the name from the first
    assert b.founded_year == 2008 and b.name == "Артекс Златен век ООД"


def test_capital_is_converted_from_eur(session):
    e, _ = entity_for_company(session, "111222333", name="X", capital_eur=1000)
    assert float(e.capital_bgn) == 1955.83


def test_person_upserts_on_person_key(session):
    p1, made = entity_for_person(session, "Иван Иванов", "abc-1")
    p2, made2 = entity_for_person(session, "Иван Иванов", "abc-1")
    assert made is True and made2 is False and p1.id == p2.id


def test_edge_upserts_on_natural_key(session):
    a, _ = entity_for_company(session, "111", name="A")
    b, _ = entity_for_company(session, "222", name="B")
    e1 = upsert_edge(session, a.id, b.id, "ownership", share_pct=50)
    e2 = upsert_edge(session, a.id, b.id, "ownership", share_pct=75)
    assert e1.id == e2.id and float(e2.share_pct) == 75
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_app_entities.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.entities'`

- [ ] **Step 3: Create `backend/app/names.py`**

```python
"""Loose name normalisation, shared by the API and the ETL.

Lives in ``app`` rather than ``etl`` so the deployed API never has to import the
ETL package. ``etl.load_phase3`` re-exports it as ``_norm_name`` for its callers.
"""

from __future__ import annotations

import re
from typing import Optional


def norm_name(name: Optional[str]) -> str:
    """Loose company-name key for matching a project's developer to a builder."""
    if not name:
        return ""
    name = re.sub(r"[\"'„“”«»]", "", name.lower())
    # drop common legal-form suffixes
    name = re.sub(r"\b(оод|еоод|ад|еад|ет|кд|сд|ltd|ood|eood|ad|ead)\b", " ", name)
    return re.sub(r"\s+", " ", name).strip()
```

- [ ] **Step 4: Create `backend/app/entities.py`**

Move the bodies of `entity_for_builder`, `entity_for_company`, `entity_for_person`, `upsert_edge` and the `BGN_PER_EUR` constant out of `backend/etl/entities.py` **verbatim** — do not change a line of logic. Header:

```python
"""Natural-key entity helpers — get-or-create companies, persons and edges.

Shared by the ETL (batch loads from ``data/raw``) and the sync API (bundles
pushed from the MacBook). Every function is idempotent on a natural key —
ЕИК for companies, ``person_key`` for persons, ``(src, dst, relation,
valid_from)`` for edges — and enriches an existing row rather than replacing it,
so re-running is always safe.
"""

from __future__ import annotations

from datetime import date
from typing import Optional, Tuple

from sqlalchemy import and_, select

from app.models import Builder, Entity, EntityEdge
from app.names import norm_name as _norm_name
from app.slugs import slugify

BGN_PER_EUR = 1.95583  # fixed peg (matches the crawlers)
```

Then the four functions, copied unchanged.

- [ ] **Step 5: Re-export from `backend/etl/entities.py`**

Delete the four moved function bodies and the `BGN_PER_EUR` line. Replace the `from app.slugs import slugify` / `from etl.load_phase3 import _norm_name` imports with:

```python
from app.entities import (  # noqa: F401 — re-exported for existing ETL callers
    BGN_PER_EUR,
    entity_for_builder,
    entity_for_company,
    entity_for_person,
    upsert_edge,
)
```

Keep everything else in the file (`OwnershipReport`, `load_ownership`, `_load_person_participations`) exactly as it is. Keep any imports those still need (`select`, `date`, `dataclass`, `Iterable`).

- [ ] **Step 6: Point `backend/etl/load_phase3.py` at the new module**

Delete the `_norm_name` function body (lines 49-56) and add to the imports:

```python
from app.names import norm_name as _norm_name  # noqa: F401 — re-exported
```

- [ ] **Step 7: Run the new test plus the whole suite**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: PASS — new file green, and every pre-existing test still green (this is a pure move; any failure means logic changed).

- [ ] **Step 8: Commit**

```bash
git add backend/app/names.py backend/app/entities.py backend/etl/entities.py \
        backend/etl/load_phase3.py backend/tests/test_app_entities.py
git commit -m "refactor(entities): move natural-key helpers from etl to app

The sync API needs get-or-create-by-ЕИК/person_key and must not import the
ETL package. Pure move: etl/entities.py re-exports, no logic changed.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Schema — delivery fields on `research_request` + `sync_log`

**Files:**
- Modify: `backend/app/models.py` (add three columns to `ResearchRequest`, add `SyncLog`)
- Create: `backend/alembic/versions/b3c4d5e6f7a8_sync_log_and_request_delivery.py`
- Test: `backend/tests/test_sync_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `app.models.SyncLog` with columns `id, request_id, action, dry_run, summary, created_at`; `ResearchRequest.report_md`, `.notes`, `.delivered_at`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_sync_models.py`:

```python
"""Delivery fields on research_request + the sync audit log."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import ResearchRequest, SyncLog


@pytest.fixture
def session():
    engine = create_engine("sqlite://", future=True,
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, future=True)()
    yield s
    s.close()


def test_request_carries_delivery_fields(session):
    r = ResearchRequest(company_name="X", requester_email="a@b.c",
                        report_md="# findings", notes="internal",
                        delivered_at=datetime(2026, 8, 20, 10, 0))
    session.add(r)
    session.commit()
    assert r.report_md == "# findings" and r.notes == "internal"
    assert r.delivered_at.year == 2026


def test_sync_log_stores_a_json_summary(session):
    log = SyncLog(action="findings", dry_run=True,
                  summary={"tables": {"entity": {"created": 2}}})
    session.add(log)
    session.commit()
    assert log.summary["tables"]["entity"]["created"] == 2
    assert log.dry_run is True and log.request_id is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_sync_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'SyncLog'`

- [ ] **Step 3: Add the columns and the model**

In `backend/app/models.py`, add to `ResearchRequest` just above `created_at`:

```python
    # Delivery: what we sent back, and when. Written by the sync API when a
    # findings bundle is applied (see app/sync/router.py).
    report_md: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
```

At the end of the file:

```python
# --- Sync audit log ----------------------------------------------------------
# Every bundle pushed from the MacBook lands here, dry-runs included, so there is
# a record of what was applied to production and when. ``summary`` is the diff
# report the endpoint returned (counts per table + the first N field changes).


class SyncLog(Base):
    """One push from the research machine to production."""

    __tablename__ = "sync_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("research_request.id"), index=True, nullable=True
    )
    action: Mapped[str] = mapped_column(String, nullable=False)  # 'findings' | 'bundle'
    dry_run: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    summary: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
```

`JSON`, `Boolean`, `false`, `ForeignKey`, `String`, `Text` are already imported in this file — verify before adding any import.

- [ ] **Step 4: Create the migration**

`backend/alembic/versions/b3c4d5e6f7a8_sync_log_and_request_delivery.py`:

```python
"""sync_log + research_request delivery fields

Revision ID: b3c4d5e6f7a8
Revises: a1b2c3d4e5f7
Create Date: 2026-08-20

Adds the delivery record (what we sent back for a request) and the audit log of
every bundle pushed from the research machine.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("research_request", sa.Column("report_md", sa.Text(), nullable=True))
    op.add_column("research_request", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column("research_request", sa.Column("delivered_at", sa.DateTime(), nullable=True))

    op.create_table(
        "sync_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.Integer(),
                  sa.ForeignKey("research_request.id"), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_sync_log_request_id", "sync_log", ["request_id"])


def downgrade() -> None:
    op.drop_index("ix_sync_log_request_id", table_name="sync_log")
    op.drop_table("sync_log")
    op.drop_column("research_request", "delivered_at")
    op.drop_column("research_request", "notes")
    op.drop_column("research_request", "report_md")
```

- [ ] **Step 5: Run the test and apply the migration locally**

```bash
cd backend && .venv/bin/python -m pytest tests/test_sync_models.py -v
.venv/bin/alembic upgrade head
.venv/bin/alembic current
```
Expected: tests PASS; `alembic current` prints `b3c4d5e6f7a8 (head)`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models.py backend/alembic/versions/b3c4d5e6f7a8_sync_log_and_request_delivery.py \
        backend/tests/test_sync_models.py
git commit -m "feat(sync): research_request delivery fields + sync_log table

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Bundle schemas and validation

**Files:**
- Create: `backend/app/sync/__init__.py` (empty)
- Create: `backend/app/sync/schemas.py`
- Test: `backend/tests/test_sync_schemas.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `app.sync.schemas.{EntityRef, EntityIn, BuilderIn, EdgeIn, SignalIn, CourtCheckIn, Bundle}`. `Bundle` fields: `entities: list[EntityIn]`, `builder: Optional[BuilderIn]`, `edges: list[EdgeIn]`, `signals: list[SignalIn]`, `court_checks: list[CourtCheckIn]`, `report_md: Optional[str]`, `notes: Optional[str]` — all collections default to `[]`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_sync_schemas.py`:

```python
"""Bundle validation. Structural rules fail loudly here, before any DB work."""

import pytest
from pydantic import ValidationError

from app.sync.schemas import Bundle


def test_empty_bundle_is_valid():
    b = Bundle()
    assert b.entities == [] and b.edges == [] and b.builder is None


def test_company_entity_requires_eik():
    with pytest.raises(ValidationError, match="eik"):
        Bundle(entities=[{"kind": "company", "name": "Артекс ООД"}])


def test_person_entity_requires_person_key():
    # A keyless person would create a duplicate node on every re-push, and a
    # fuzzy name fallback could merge two different people. Fail instead.
    with pytest.raises(ValidationError, match="person_key"):
        Bundle(entities=[{"kind": "person", "name": "Иван Иванов"}])


def test_edge_ref_needs_exactly_one_key():
    with pytest.raises(ValidationError, match="eik"):
        Bundle(edges=[{"src": {}, "dst": {"eik": "111"}, "relation": "ownership"}])


def test_full_bundle_parses():
    b = Bundle(**{
        "entities": [
            {"kind": "company", "eik": "175376051", "name": "Артекс Златен век ООД",
             "legal_form": "ООД", "capital_eur": 5000, "founded_year": 2008,
             "source": "papagal"},
            {"kind": "person", "person_key": "175376051-2", "name": "Иван Иванов"},
        ],
        "builder": {"eik": "175376051", "name": "Артекс Златен век ООД",
                    "insolvency_flag": False},
        "edges": [{"src": {"person_key": "175376051-2"}, "dst": {"eik": "175376051"},
                   "relation": "ownership", "share_pct": 50,
                   "valid_from": "2008-01-01"}],
        "signals": [{"subject_kind": "company", "matched_name": "Артекс Златен век ООД",
                     "matched_eik": "175376051", "source_type": "registry",
                     "tier": "official", "match_confidence": "eik",
                     "url": "https://legalacts.justice.bg/Search/GetAct?actId=123"}],
        "court_checks": [{"eik": "175376051", "method": "eik", "acts_found": 3,
                          "checked_at": "2026-08-20T10:00:00"}],
        "report_md": "# Findings",
        "notes": "internal",
    })
    assert b.entities[0].capital_eur == 5000
    assert b.edges[0].src.person_key == "175376051-2"
    assert b.court_checks[0].acts_found == 3
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_sync_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.sync'`

- [ ] **Step 3: Create the package and schemas**

`backend/app/sync/__init__.py` — empty file.

`backend/app/sync/schemas.py`:

```python
"""Wire format for a findings bundle pushed from the research machine.

Entities are addressed by **natural key** — ЕИК for companies, ``person_key``
for persons — never by database id, because local ids and production ids are
unrelated. Edges name their endpoints the same way and the server resolves them.

Structural rules that would corrupt production are enforced here, before any
database work: a company without an ЕИК cannot be deduplicated, and a person
without a ``person_key`` would either duplicate on every re-push or (with a
fuzzy name fallback) merge two different people.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EntityRef(BaseModel):
    """Points at an entity by natural key. Exactly one of the two is required."""

    model_config = ConfigDict(extra="forbid")

    eik: Optional[str] = None
    person_key: Optional[str] = None

    @model_validator(mode="after")
    def _exactly_one_key(self) -> "EntityRef":
        if bool(self.eik) == bool(self.person_key):
            raise ValueError("entity reference needs exactly one of eik / person_key")
        return self


class EntityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["company", "person"]
    name: str
    eik: Optional[str] = None
    person_key: Optional[str] = None
    legal_form: Optional[str] = None
    status: Optional[str] = None
    address: Optional[str] = None
    capital_eur: Optional[float] = None   # converted to capital_bgn at the peg
    founded_year: Optional[int] = None
    source: Optional[str] = None

    @model_validator(mode="after")
    def _key_matches_kind(self) -> "EntityIn":
        if self.kind == "company" and not self.eik:
            raise ValueError("company entity requires eik")
        if self.kind == "person" and not self.person_key:
            raise ValueError("person entity requires person_key")
        return self


class BuilderIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eik: str
    name: str
    legal_form: Optional[str] = None
    address: Optional[str] = None
    capital_bgn: Optional[float] = None
    status: Optional[str] = None
    ksb_category: Optional[str] = None
    ksb_active: Optional[bool] = None
    insolvency_flag: Optional[bool] = None
    tax_debt_bgn: Optional[float] = None


class EdgeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    src: EntityRef
    dst: EntityRef
    relation: Literal["ownership", "management"]
    share_pct: Optional[float] = None
    role: Optional[str] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    is_current: bool = True
    source: Optional[str] = None


class SignalIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_kind: Literal["company", "person"]
    matched_name: str
    url: str
    source_type: str          # registry | forum | web
    tier: str                 # official | community | web
    match_confidence: str     # eik | fuzzy_high | fuzzy_low
    matched_eik: Optional[str] = None
    matched_person_key: Optional[str] = None
    title: Optional[str] = None
    snippet: Optional[str] = None
    source_site: Optional[str] = None
    observed_date: Optional[date] = None
    scraped_at: Optional[datetime] = None


class CourtCheckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eik: str
    checked_at: datetime
    name: Optional[str] = None
    method: str = "eik"
    acts_found: int = 0
    source_site: str = "legalacts.justice.bg"


class Bundle(BaseModel):
    """Everything one research session produced, applied in one transaction."""

    model_config = ConfigDict(extra="forbid")

    entities: List[EntityIn] = Field(default_factory=list)
    builder: Optional[BuilderIn] = None
    edges: List[EdgeIn] = Field(default_factory=list)
    signals: List[SignalIn] = Field(default_factory=list)
    court_checks: List[CourtCheckIn] = Field(default_factory=list)
    report_md: Optional[str] = None
    notes: Optional[str] = None
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_sync_schemas.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/sync/__init__.py backend/app/sync/schemas.py backend/tests/test_sync_schemas.py
git commit -m "feat(sync): bundle wire schemas with natural-key validation

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Upsert engine — entities, builder, diff reporting

**Files:**
- Create: `backend/app/sync/upsert.py`
- Test: `backend/tests/test_sync_upsert.py`

**Interfaces:**
- Consumes: `app.sync.schemas.Bundle`; `app.entities.{entity_for_company, entity_for_person, entity_for_builder}`.
- Produces:
  - `app.sync.upsert.BundleError(Exception)`
  - `app.sync.upsert.TableStat` dataclass — `created, updated, unchanged, skipped: int`
  - `app.sync.upsert.SyncReport` dataclass — `tables: Dict[str, TableStat]`, `changes: List[dict]`, `warnings: List[str]`, method `as_dict() -> dict`
  - `app.sync.upsert.apply_bundle(session, bundle: Bundle) -> SyncReport` — flushes, never commits; raises `BundleError` on unresolvable references
  - `app.sync.upsert.MAX_CHANGES: int = 200`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_sync_upsert.py`:

```python
"""The upsert engine: natural-key writes, a field-level diff, and idempotency.

No FastAPI here — apply_bundle takes a session and flushes. Transaction control
(commit vs rollback for a dry run) belongs to the router.
"""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Builder, Entity
from app.sync.schemas import Bundle
from app.sync.upsert import apply_bundle


@pytest.fixture
def session():
    engine = create_engine("sqlite://", future=True,
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, future=True)()
    yield s
    s.close()


def _company(**kw):
    return {"kind": "company", "eik": "175376051", "name": "Артекс Златен век ООД", **kw}


def test_creates_a_company_entity(session):
    report = apply_bundle(session, Bundle(entities=[_company()]))
    assert report.tables["entity"].created == 1
    assert session.scalar(select(Entity).where(Entity.eik == "175376051")).name \
        == "Артекс Златен век ООД"


def test_second_identical_push_reports_unchanged(session):
    apply_bundle(session, Bundle(entities=[_company()]))
    report = apply_bundle(session, Bundle(entities=[_company()]))
    assert report.tables["entity"].created == 0
    assert report.tables["entity"].unchanged == 1
    assert session.scalar(select(Entity).where(Entity.eik == "175376051")) is not None


def test_update_is_reported_field_by_field(session):
    apply_bundle(session, Bundle(entities=[_company()]))
    report = apply_bundle(session, Bundle(entities=[_company(founded_year=2008)]))
    assert report.tables["entity"].updated == 1
    change = next(c for c in report.changes if c["field"] == "founded_year")
    assert change["from"] is None and change["to"] == 2008
    assert change["table"] == "entity" and change["key"] == "175376051"


def test_omitted_fields_never_erase(session):
    apply_bundle(session, Bundle(entities=[_company(address="София, ул. Х")]))
    apply_bundle(session, Bundle(entities=[_company()]))  # no address this time
    assert session.scalar(select(Entity).where(Entity.eik == "175376051")).address \
        == "София, ул. Х"


def test_builder_is_upserted_and_linked_to_its_entity(session):
    report = apply_bundle(session, Bundle(
        entities=[_company()],
        builder={"eik": "175376051", "name": "Артекс Златен век ООД",
                 "insolvency_flag": True},
    ))
    b = session.scalar(select(Builder).where(Builder.eik == "175376051"))
    assert b.insolvency_flag is True and b.entity_id is not None
    assert report.tables["builder"].created == 1


def test_corporate_shareholder_person_key_warns(session):
    # Papagal lists a company's own name among "related persons" with a synthetic
    # <eik>-N key. entity_for_person resolves it to the company; we warn so the
    # mis-typing is visible rather than silent.
    report = apply_bundle(session, Bundle(entities=[
        _company(),
        {"kind": "person", "person_key": "175376051-2", "name": "Артекс Златен век ООД"},
    ]))
    assert any("175376051" in w for w in report.warnings)


def test_report_serialises_to_json_safe_dict(session):
    report = apply_bundle(session, Bundle(entities=[_company(capital_eur=5000)]))
    import json
    json.dumps(report.as_dict())  # must not raise on Decimal/date
    assert report.as_dict()["tables"]["entity"]["created"] == 1
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_sync_upsert.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.sync.upsert'`

- [ ] **Step 3: Write `backend/app/sync/upsert.py`**

```python
"""Apply a findings bundle to the database, with a field-level diff.

Contract:

* **Natural keys only.** Companies key on ЕИК, persons on ``person_key``, edges
  on ``(src, dst, relation, valid_from)``, signals on ``(url, matched_name)``,
  court checks on ``(eik, source_site, checked_at)``. Local ids never appear.
* **Enrich, don't erase.** An omitted or null field never overwrites a non-null
  production value — that is what makes re-pushing a partial bundle safe.
* **Flush, never commit.** The caller owns the transaction; a dry run is the
  same code path followed by a rollback.
* **All or nothing.** An unresolvable reference raises :class:`BundleError` and
  the caller rolls back — a half-applied bundle is worse than none.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_, select

from app.entities import entity_for_builder, entity_for_company, entity_for_person
from app.entities import upsert_edge
from app.models import Builder, CourtCheck, Entity, EntityEdge, EntitySignal
from app.sync.schemas import Bundle, EntityRef

MAX_CHANGES = 200

# ``created_at`` is server-defaulted and always differs; it is noise in a diff.
_IGNORED_COLS = {"created_at"}


class BundleError(Exception):
    """The bundle cannot be applied — the caller must roll back."""


@dataclass
class TableStat:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0


@dataclass
class SyncReport:
    tables: Dict[str, TableStat] = field(default_factory=dict)
    changes: List[dict] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def stat(self, table: str) -> TableStat:
        return self.tables.setdefault(table, TableStat())

    def as_dict(self) -> dict:
        return {
            "tables": {t: vars(s) for t, s in self.tables.items()},
            "changes": self.changes,
            "warnings": self.warnings,
        }


def _json_safe(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _snapshot(obj) -> dict:
    return {c.key: getattr(obj, c.key) for c in obj.__table__.columns
            if c.key not in _IGNORED_COLS}


def _record(report: SyncReport, table: str, key: str,
            before: Optional[dict], after: dict) -> None:
    """Fold one object's before/after into the report."""
    stat = report.stat(table)
    if before is None:
        stat.created += 1
        return
    changed = [(k, before.get(k), after[k]) for k in after if before.get(k) != after[k]]
    if not changed:
        stat.unchanged += 1
        return
    stat.updated += 1
    for name, old, new in changed:
        if len(report.changes) < MAX_CHANGES:
            report.changes.append({"table": table, "key": key, "field": name,
                                   "from": _json_safe(old), "to": _json_safe(new)})


def apply_bundle(session, bundle: Bundle) -> SyncReport:
    """Apply every part of ``bundle``. Flushes; the caller commits or rolls back."""
    report = SyncReport()
    resolved = _apply_entities(session, bundle, report)
    _apply_builder(session, bundle, report, resolved)
    _apply_edges(session, bundle, report, resolved)
    _apply_signals(session, bundle, report)
    _apply_court_checks(session, bundle, report)
    return report


def _apply_entities(session, bundle: Bundle, report: SyncReport
                    ) -> Dict[Tuple[str, str], int]:
    """Upsert every entity; return a natural-key -> id map for the edge pass."""
    resolved: Dict[Tuple[str, str], int] = {}
    for e in bundle.entities:
        if e.kind == "company":
            existing = session.scalar(select(Entity).where(Entity.eik == e.eik))
            before = _snapshot(existing) if existing is not None else None
            ent, _ = entity_for_company(
                session, e.eik, name=e.name, legal_form=e.legal_form, status=e.status,
                address=e.address, capital_eur=e.capital_eur,
                founded_year=e.founded_year, source=e.source,
            )
            _record(report, "entity", e.eik, before, _snapshot(ent))
            resolved[("eik", e.eik)] = ent.id
            continue

        prefix = e.person_key.split("-")[0]
        if prefix.isdigit() and session.scalar(
            select(Entity.id).where(Entity.eik == prefix, Entity.kind == "company")
        ):
            report.warnings.append(
                f"person_key {e.person_key} resolves to company ЕИК {prefix} — "
                "corporate shareholder listed as a person?"
            )
        existing = session.scalar(
            select(Entity).where(Entity.person_key == e.person_key)
        )
        before = _snapshot(existing) if existing is not None else None
        ent, _ = entity_for_person(session, e.name, e.person_key, source=e.source)
        _record(report, "entity", e.person_key, before, _snapshot(ent))
        resolved[("person_key", e.person_key)] = ent.id
    return resolved


def _apply_builder(session, bundle: Bundle, report: SyncReport,
                   resolved: Dict[Tuple[str, str], int]) -> None:
    b = bundle.builder
    if b is None:
        return
    existing = session.scalar(select(Builder).where(Builder.eik == b.eik))
    before = _snapshot(existing) if existing is not None else None
    builder = existing
    if builder is None:
        builder = Builder(eik=b.eik, name=b.name)
        session.add(builder)
    # enrich, don't erase
    for attr in ("name", "legal_form", "address", "capital_bgn", "status",
                 "ksb_category", "ksb_active", "insolvency_flag", "tax_debt_bgn"):
        value = getattr(b, attr)
        if value is not None:
            setattr(builder, attr, value)
    session.flush()
    entity_for_builder(session, builder)  # links builder.entity_id, mirrors identity
    session.flush()
    _record(report, "builder", b.eik, before, _snapshot(builder))
```

The remaining three functions (`_apply_edges`, `_apply_signals`, `_apply_court_checks`) are Task 5. For this task, define them as no-op stubs at the bottom so `apply_bundle` runs:

```python
def _apply_edges(session, bundle, report, resolved):
    pass


def _apply_signals(session, bundle, report):
    pass


def _apply_court_checks(session, bundle, report):
    pass
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_sync_upsert.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/sync/upsert.py backend/tests/test_sync_upsert.py
git commit -m "feat(sync): upsert engine for entities and builder, with field-level diff

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: Upsert engine — edges, signals, court checks

**Files:**
- Modify: `backend/app/sync/upsert.py` (replace the three stubs)
- Test: `backend/tests/test_sync_upsert_graph.py`

**Interfaces:**
- Consumes: `SyncReport`, `BundleError`, `_record`, `_snapshot` from Task 4; `app.entities.upsert_edge`.
- Produces: no new public names — `apply_bundle` now covers `entity_edge`, `entity_signal` and `court_check` in its report tables.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_sync_upsert_graph.py`:

```python
"""Edges, signals and court checks — the parts of a bundle that reference
entities by natural key and must stay idempotent across re-pushes."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import CourtCheck, EntityEdge, EntitySignal
from app.sync.schemas import Bundle
from app.sync.upsert import BundleError, apply_bundle


@pytest.fixture
def session():
    engine = create_engine("sqlite://", future=True,
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, future=True)()
    yield s
    s.close()


ENTITIES = [
    {"kind": "company", "eik": "175376051", "name": "Артекс Златен век ООД"},
    {"kind": "person", "person_key": "p-1", "name": "Иван Иванов"},
]


def test_edge_resolves_entities_created_in_the_same_bundle(session):
    report = apply_bundle(session, Bundle(entities=ENTITIES, edges=[
        {"src": {"person_key": "p-1"}, "dst": {"eik": "175376051"},
         "relation": "ownership", "share_pct": 50},
    ]))
    edge = session.scalar(select(EntityEdge))
    assert edge is not None and float(edge.share_pct) == 50
    assert report.tables["entity_edge"].created == 1


def test_edge_to_an_unknown_entity_raises(session):
    with pytest.raises(BundleError, match="999999999"):
        apply_bundle(session, Bundle(entities=ENTITIES, edges=[
            {"src": {"eik": "999999999"}, "dst": {"eik": "175376051"},
             "relation": "ownership"},
        ]))


def test_signal_upserts_on_url_and_matched_name(session):
    sig = {"subject_kind": "company", "matched_name": "Артекс Златен век ООД",
           "matched_eik": "175376051", "source_type": "registry", "tier": "official",
           "match_confidence": "eik",
           "url": "https://legalacts.justice.bg/Search/GetAct?actId=123"}
    apply_bundle(session, Bundle(entities=ENTITIES, signals=[sig]))
    apply_bundle(session, Bundle(entities=ENTITIES, signals=[sig]))
    assert session.scalar(select(func.count()).select_from(EntitySignal)) == 1
    assert session.scalar(select(EntitySignal)).entity_id is not None


def test_same_act_url_can_belong_to_two_companies(session):
    # One court actId legitimately names several companies. The key is
    # (url, matched_name), so both rows survive.
    url = "https://legalacts.justice.bg/Search/GetAct?actId=123"
    apply_bundle(session, Bundle(
        entities=[{"kind": "company", "eik": "111", "name": "А ООД"},
                  {"kind": "company", "eik": "222", "name": "Б ООД"}],
        signals=[
            {"subject_kind": "company", "matched_name": "А ООД", "matched_eik": "111",
             "source_type": "registry", "tier": "official",
             "match_confidence": "eik", "url": url},
            {"subject_kind": "company", "matched_name": "Б ООД", "matched_eik": "222",
             "source_type": "registry", "tier": "official",
             "match_confidence": "eik", "url": url},
        ]))
    rows = session.scalars(select(EntitySignal)).all()
    assert len(rows) == 2
    assert {r.matched_eik for r in rows} == {"111", "222"}
    assert len({r.entity_id for r in rows}) == 2  # resolved per entity, not per url


def test_court_check_is_appended_once_per_distinct_check(session):
    check = {"eik": "175376051", "checked_at": "2026-08-20T10:00:00",
             "method": "eik", "acts_found": 3}
    apply_bundle(session, Bundle(entities=ENTITIES, court_checks=[check]))
    report = apply_bundle(session, Bundle(entities=ENTITIES, court_checks=[check]))
    assert session.scalar(select(func.count()).select_from(CourtCheck)) == 1
    assert report.tables["court_check"].skipped == 1

    later = dict(check, checked_at="2026-08-21T10:00:00")
    apply_bundle(session, Bundle(entities=ENTITIES, court_checks=[later]))
    assert session.scalar(select(func.count()).select_from(CourtCheck)) == 2
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_sync_upsert_graph.py -v`
Expected: FAIL — edges/signals/court checks are stubs, so `report.tables["entity_edge"]` raises `KeyError` and no rows are written.

- [ ] **Step 3: Replace the three stubs in `backend/app/sync/upsert.py`**

```python
def _resolve_ref(session, ref: EntityRef, resolved: Dict[Tuple[str, str], int]) -> int:
    """Natural key -> entity id, preferring entities created in this bundle."""
    key = ("eik", ref.eik) if ref.eik else ("person_key", ref.person_key)
    if key in resolved:
        return resolved[key]
    column = Entity.eik if ref.eik else Entity.person_key
    entity = session.scalar(select(Entity).where(column == key[1]))
    if entity is None:
        raise BundleError(
            f"edge references unknown entity ({key[0]}={key[1]}) — include it in "
            "the bundle's entities, or push it first"
        )
    resolved[key] = entity.id
    return entity.id


def _apply_edges(session, bundle: Bundle, report: SyncReport,
                 resolved: Dict[Tuple[str, str], int]) -> None:
    for e in bundle.edges:
        src_id = _resolve_ref(session, e.src, resolved)
        dst_id = _resolve_ref(session, e.dst, resolved)
        existing = session.scalar(select(EntityEdge).where(and_(
            EntityEdge.src_entity_id == src_id,
            EntityEdge.dst_entity_id == dst_id,
            EntityEdge.relation == e.relation,
            EntityEdge.valid_from.is_(None) if e.valid_from is None
            else EntityEdge.valid_from == e.valid_from,
        )))
        before = _snapshot(existing) if existing is not None else None
        edge = upsert_edge(
            session, src_id, dst_id, e.relation, share_pct=e.share_pct, role=e.role,
            valid_from=e.valid_from, valid_to=e.valid_to, is_current=e.is_current,
            source=e.source,
        )
        _record(report, "entity_edge", f"{src_id}->{dst_id}:{e.relation}",
                before, _snapshot(edge))


def _apply_signals(session, bundle: Bundle, report: SyncReport) -> None:
    """Upsert on (url, matched_name).

    ``entity_id`` is resolved **per signal** from its own ЕИК / person_key — never
    from the url. One court act legitimately names several companies, and matching
    on the url alone reassigns every one of them to whichever entity came last.
    """
    for s in bundle.signals:
        entity_id = None
        if s.matched_eik:
            entity_id = session.scalar(
                select(Entity.id).where(Entity.eik == s.matched_eik)
            )
        if entity_id is None and s.matched_person_key:
            entity_id = session.scalar(
                select(Entity.id).where(Entity.person_key == s.matched_person_key)
            )

        existing = session.scalar(select(EntitySignal).where(and_(
            EntitySignal.url == s.url,
            EntitySignal.matched_name == s.matched_name,
        )))
        before = _snapshot(existing) if existing is not None else None
        signal = existing
        if signal is None:
            signal = EntitySignal(url=s.url, matched_name=s.matched_name,
                                  subject_kind=s.subject_kind, source_type=s.source_type,
                                  tier=s.tier, match_confidence=s.match_confidence)
            session.add(signal)
        for attr in ("subject_kind", "source_type", "tier", "match_confidence",
                     "matched_eik", "matched_person_key", "title", "snippet",
                     "source_site", "observed_date", "scraped_at"):
            value = getattr(s, attr)
            if value is not None:
                setattr(signal, attr, value)
        if entity_id is not None:
            signal.entity_id = entity_id
        session.flush()
        _record(report, "entity_signal", f"{s.url}|{s.matched_name}",
                before, _snapshot(signal))


def _apply_court_checks(session, bundle: Bundle, report: SyncReport) -> None:
    """Append-only log of searches performed.

    Keyed on the exact ``(eik, source_site, checked_at)`` triple so re-pushing the
    same bundle is a no-op, while a genuinely later check appends a new row.
    """
    for c in bundle.court_checks:
        existing = session.scalar(select(CourtCheck).where(and_(
            CourtCheck.eik == c.eik,
            CourtCheck.source_site == c.source_site,
            CourtCheck.checked_at == c.checked_at,
        )))
        if existing is not None:
            report.stat("court_check").skipped += 1
            continue
        session.add(CourtCheck(eik=c.eik, name=c.name, method=c.method,
                               acts_found=c.acts_found, source_site=c.source_site,
                               checked_at=c.checked_at))
        session.flush()
        report.stat("court_check").created += 1
```

- [ ] **Step 4: Run both upsert test files**

Run: `cd backend && .venv/bin/python -m pytest tests/test_sync_upsert.py tests/test_sync_upsert_graph.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/sync/upsert.py backend/tests/test_sync_upsert_graph.py
git commit -m "feat(sync): upsert edges, signals and court checks by natural key

Signals resolve entity_id per signal, never by url — one court actId names
several companies and url-matching reassigns all of them to the last one.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Token auth that fails closed

**Files:**
- Create: `backend/app/sync/auth.py`
- Test: `backend/tests/test_sync_auth.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `app.sync.auth.require_sync_token(x_sync_token: str = Header(default="")) -> None` — a FastAPI dependency raising `HTTPException(403)`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_sync_auth.py`:

```python
"""The sync token gate. Fails closed: no env var configured means no access,
so a half-configured deploy can never leave the write endpoints open."""

import pytest
from fastapi import HTTPException

from app.sync.auth import require_sync_token


def test_rejects_when_env_var_is_unset(monkeypatch):
    monkeypatch.delenv("RESEARCH_API_TOKEN", raising=False)
    with pytest.raises(HTTPException) as exc:
        require_sync_token("anything")
    assert exc.value.status_code == 403


def test_rejects_an_empty_token(monkeypatch):
    monkeypatch.setenv("RESEARCH_API_TOKEN", "s3cret")
    with pytest.raises(HTTPException) as exc:
        require_sync_token("")
    assert exc.value.status_code == 403


def test_rejects_a_wrong_token(monkeypatch):
    monkeypatch.setenv("RESEARCH_API_TOKEN", "s3cret")
    with pytest.raises(HTTPException):
        require_sync_token("wrong")


def test_accepts_the_right_token(monkeypatch):
    monkeypatch.setenv("RESEARCH_API_TOKEN", "s3cret")
    assert require_sync_token("s3cret") is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_sync_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.sync.auth'`

- [ ] **Step 3: Write `backend/app/sync/auth.py`**

```python
"""Token gate for the sync endpoints.

Defence in depth, not the only defence: nginx refuses ``/api/admin/sync/`` from
the internet and the client reaches uvicorn through an SSH tunnel. The token
means SSH access alone is still not enough.

Fails closed — an unset ``RESEARCH_API_TOKEN`` rejects everything, so a deploy
that forgot the secret is unusable rather than wide open.
"""

from __future__ import annotations

import os
import secrets

from fastapi import Header, HTTPException


def require_sync_token(x_sync_token: str = Header(default="")) -> None:
    expected = os.environ.get("RESEARCH_API_TOKEN")
    if not expected or not secrets.compare_digest(x_sync_token, expected):
        raise HTTPException(status_code=403, detail="forbidden")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_sync_auth.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/sync/auth.py backend/tests/test_sync_auth.py
git commit -m "feat(sync): fail-closed token gate for the sync endpoints

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: Read endpoints — list requests, claim, look up prod state

The coverage-flag logic (`in_db`, `court_checked_at`) already exists inline in `routes.py:admin_research_requests`. Extract it so both callers share one implementation rather than duplicating a subtle query.

**Files:**
- Create: `backend/app/coverage.py`
- Create: `backend/app/sync/router.py`
- Modify: `backend/app/routes.py:1160-1215` (call the extracted helper)
- Modify: `backend/app/main.py` (mount the router)
- Test: `backend/tests/test_sync_api_read.py`

**Interfaces:**
- Consumes: `app.sync.auth.require_sync_token`; `app.db.get_session`.
- Produces:
  - `app.coverage.coverage_flags(session, requests: list[ResearchRequest]) -> Dict[int, dict]` — maps `request.id` to `{"in_db": bool, "entity_id": Optional[int], "edge_count": int, "court_checked_at": Optional[datetime], "court_acts": Optional[int]}`
  - `app.sync.router.router` — `APIRouter(prefix="/api/admin/sync")` with `GET /requests`, `POST /requests/{id}/claim`, `GET /entities`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_sync_api_read.py`:

```python
"""Read side of the sync API: what is waiting, claiming one, and what prod
already holds for a set of ЕИКs."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_session
from app.main import app
from app.models import CourtCheck, Entity, ResearchRequest, User

HEADERS = {"X-Sync-Token": "s3cret"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("RESEARCH_API_TOKEN", "s3cret")
    engine = create_engine("sqlite://", future=True,
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, future=True)()
    s.add_all([
        ResearchRequest(company_name="Артекс", company_eik="175376051",
                        requester_email="a@b.c", status="new"),
        ResearchRequest(company_name="Друга", requester_email="d@e.f",
                        status="delivered"),
        Entity(kind="company", eik="175376051", name="Артекс Златен век ООД"),
        CourtCheck(eik="175376051", acts_found=3,
                   checked_at=datetime(2026, 8, 1, 10, 0)),
        User(email="u@example.com", hashed_password="x", tier="member",
             is_active=True, is_superuser=False, is_verified=True),
    ])
    s.commit()
    app.dependency_overrides[get_session] = lambda: s
    yield TestClient(app)
    app.dependency_overrides.pop(get_session, None)
    s.close()


def test_requires_the_token(client):
    assert client.get("/api/admin/sync/requests").status_code == 403
    assert client.get("/api/admin/sync/requests",
                      headers={"X-Sync-Token": "nope"}).status_code == 403


def test_lists_new_requests_with_coverage_flags(client):
    rows = client.get("/api/admin/sync/requests", headers=HEADERS).json()
    assert len(rows) == 1 and rows[0]["company_eik"] == "175376051"
    assert rows[0]["in_db"] is True
    assert rows[0]["court_checked_at"].startswith("2026-08-01")
    assert rows[0]["court_acts"] == 3


def test_status_filter_all_returns_everything(client):
    rows = client.get("/api/admin/sync/requests?status=all", headers=HEADERS).json()
    assert len(rows) == 2


def test_claim_moves_new_to_in_progress_and_is_idempotent(client):
    first = client.post("/api/admin/sync/requests/1/claim", headers=HEADERS)
    assert first.status_code == 200 and first.json()["status"] == "in_progress"
    again = client.post("/api/admin/sync/requests/1/claim", headers=HEADERS)
    assert again.status_code == 200 and again.json()["status"] == "in_progress"


def test_claiming_a_delivered_request_conflicts(client):
    assert client.post("/api/admin/sync/requests/2/claim",
                       headers=HEADERS).status_code == 409


def test_entity_lookup_reports_what_prod_holds(client):
    body = client.get("/api/admin/sync/entities?eik=175376051&eik=999999999",
                      headers=HEADERS).json()
    assert body["175376051"]["name"] == "Артекс Златен век ООД"
    assert body["175376051"]["edge_count"] == 0
    assert body["175376051"]["last_court_check"].startswith("2026-08-01")
    assert body["999999999"] is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_sync_api_read.py -v`
Expected: FAIL — 404 on every route (`app.sync.router` does not exist / is not mounted).

- [ ] **Step 3: Extract the coverage helper into `backend/app/coverage.py`**

Move the body of the flag computation out of `routes.py:admin_research_requests` verbatim:

```python
"""Coverage flags for a set of research requests.

Answers two questions the admin inbox and the sync client both ask: do we hold
this company, and when did we last run a court search for its ЕИК?

The court flag reads ``court_check`` — the log of searches performed — **not**
signal presence. A search that finds no acts writes no signal and would
otherwise look like "never checked".
"""

from __future__ import annotations

from typing import Dict, List

from sqlalchemy import func, select

from app.models import CourtCheck, Entity, EntityEdge, ResearchRequest


def coverage_flags(session, requests: List[ResearchRequest]) -> Dict[int, dict]:
    """Map ``request.id`` -> coverage dict. Requests without an ЕИК get zeroes."""
    blank = {"in_db": False, "entity_id": None, "edge_count": 0,
             "court_checked_at": None, "court_acts": None}
    eiks = {r.company_eik for r in requests if r.company_eik}
    if not eiks:
        return {r.id: dict(blank) for r in requests}

    entities = {
        e.eik: e for e in session.scalars(select(Entity).where(Entity.eik.in_(eiks))).all()
    }
    edges: Dict[int, int] = {}
    ids = [e.id for e in entities.values()]
    if ids:
        src = select(EntityEdge.src_entity_id.label("eid"), func.count().label("n")) \
            .where(EntityEdge.src_entity_id.in_(ids)).group_by(EntityEdge.src_entity_id)
        dst = select(EntityEdge.dst_entity_id.label("eid"), func.count().label("n")) \
            .where(EntityEdge.dst_entity_id.in_(ids)).group_by(EntityEdge.dst_entity_id)
        for eid, n in session.execute(src.union_all(dst)).all():
            edges[eid] = edges.get(eid, 0) + n

    # Latest check per ЕИК: newest checked_at wins, with that run's act count.
    checks: Dict[str, tuple] = {}
    rows = session.execute(
        select(CourtCheck.eik, CourtCheck.checked_at, CourtCheck.acts_found)
        .where(CourtCheck.eik.in_(eiks))
        .order_by(CourtCheck.eik, CourtCheck.checked_at.desc())
    ).all()
    for eik, checked_at, acts in rows:
        if eik not in checks:
            checks[eik] = (checked_at, acts)

    out: Dict[int, dict] = {}
    for r in requests:
        flags = dict(blank)
        ent = entities.get(r.company_eik) if r.company_eik else None
        if ent is not None:
            flags["in_db"] = True
            flags["entity_id"] = ent.id
            flags["edge_count"] = edges.get(ent.id, 0)
        if r.company_eik and r.company_eik in checks:
            flags["court_checked_at"], flags["court_acts"] = checks[r.company_eik]
        out[r.id] = flags
    return out
```

Then rewrite the body of `admin_research_requests` in `routes.py` to use it, keeping its existing docstring and response model:

```python
    requests = session.scalars(
        select(ResearchRequest).order_by(ResearchRequest.created_at.desc()).limit(limit)
    ).all()
    flags = coverage_flags(session, requests)
    out = []
    for r in requests:
        row = AdminResearchRequestRead.model_validate(r)
        for key, value in flags[r.id].items():
            setattr(row, key, value)
        out.append(row)
    return out
```

Add `from app.coverage import coverage_flags` to the imports. Remove now-unused imports from `routes.py` only if nothing else uses them.

- [ ] **Step 4: Write `backend/app/sync/router.py`**

```python
"""Sync endpoints — the MacBook's window onto production.

Mounted at ``/api/admin/sync`` and gated by :func:`require_sync_token`. Nginx
refuses this prefix from the internet; the client reaches it through an SSH
tunnel (see ``deploy/SYNC_API.md``).

Nothing here touches ``user`` or ``oauth_account``.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from app.coverage import coverage_flags
from app.db import get_session
from app.models import CourtCheck, Entity, EntityEdge, EntitySignal, ResearchRequest
from app.sync.auth import require_sync_token

router = APIRouter(
    prefix="/api/admin/sync",
    tags=["sync"],
    dependencies=[Depends(require_sync_token)],
)


@router.get("/requests")
def list_requests(
    status: str = Query("new", description="a status value, or 'all'"),
    limit: int = Query(200, ge=1, le=2000),
    session=Depends(get_session),
):
    """Requests waiting for research, newest first, with coverage flags."""
    stmt = select(ResearchRequest).order_by(ResearchRequest.created_at.desc()).limit(limit)
    if status != "all":
        stmt = stmt.where(ResearchRequest.status == status)
    requests = session.scalars(stmt).all()
    flags = coverage_flags(session, requests)
    return [
        {
            "id": r.id, "company_name": r.company_name, "company_eik": r.company_eik,
            "owner": r.owner, "details": r.details, "search_query": r.search_query,
            "requester_name": r.requester_name, "requester_email": r.requester_email,
            "status": r.status, "order_type": r.order_type, "scope": r.scope,
            "search_type": r.search_type, "network_depth": r.network_depth,
            "entity_count": r.entity_count,
            "price_eur": float(r.price_eur) if r.price_eur is not None else None,
            "expedited": r.expedited, "created_at": r.created_at,
            "delivered_at": r.delivered_at,
            **flags[r.id],
        }
        for r in requests
    ]


@router.post("/requests/{request_id}/claim")
def claim_request(request_id: int, session=Depends(get_session)):
    """Mark a request as being worked on. Idempotent; refuses a delivered one."""
    req = session.get(ResearchRequest, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="unknown request")
    if req.status == "delivered":
        raise HTTPException(status_code=409, detail="request already delivered")
    req.status = "in_progress"
    session.commit()
    return {"id": req.id, "status": req.status}


@router.get("/entities")
def lookup_entities(
    eik: List[str] = Query(default=[]),
    session=Depends(get_session),
):
    """What production already holds per ЕИК — so a push can be diffed first."""
    out: dict[str, Optional[dict]] = {e: None for e in eik}
    if not eik:
        return out
    for entity in session.scalars(select(Entity).where(Entity.eik.in_(eik))).all():
        edge_count = session.scalar(
            select(func.count()).select_from(EntityEdge).where(
                (EntityEdge.src_entity_id == entity.id)
                | (EntityEdge.dst_entity_id == entity.id)
            )
        )
        signal_count = session.scalar(
            select(func.count()).select_from(EntitySignal)
            .where(EntitySignal.entity_id == entity.id)
        )
        last_check = session.scalar(
            select(func.max(CourtCheck.checked_at)).where(CourtCheck.eik == entity.eik)
        )
        out[entity.eik] = {
            "id": entity.id, "name": entity.name, "kind": entity.kind,
            "is_builder": entity.is_builder, "status": entity.status,
            "legal_form": entity.legal_form, "founded_year": entity.founded_year,
            "edge_count": edge_count, "signal_count": signal_count,
            "last_court_check": last_check,
        }
    return out
```

- [ ] **Step 5: Mount it in `backend/app/main.py`**

Add the import next to the existing router imports and mount it after `app.include_router(router)`:

```python
from app.sync.router import router as sync_router
...
app.include_router(sync_router)
```

- [ ] **Step 6: Run the new tests plus the existing admin tests**

Run: `cd backend && .venv/bin/python -m pytest tests/test_sync_api_read.py tests/test_admin.py tests/test_admin_coverage_flags.py -v`
Expected: PASS — the new file green, and the two admin files still green (the coverage extraction must not change their behaviour).

- [ ] **Step 7: Commit**

```bash
git add backend/app/coverage.py backend/app/sync/router.py backend/app/main.py \
        backend/app/routes.py backend/tests/test_sync_api_read.py
git commit -m "feat(sync): read endpoints for requests, claim and prod entity lookup

Coverage-flag logic extracted from routes.py into app/coverage.py so the admin
inbox and the sync client share one implementation.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: Write endpoints — findings and bulk bundle

**Files:**
- Modify: `backend/app/sync/router.py` (add two POST routes)
- Test: `backend/tests/test_sync_api_write.py`

**Interfaces:**
- Consumes: `app.sync.upsert.{apply_bundle, BundleError}`; `app.sync.schemas.Bundle`; `app.models.SyncLog`.
- Produces: `POST /api/admin/sync/requests/{id}/findings?dry_run=` and `POST /api/admin/sync/bundle?dry_run=`, both returning `{"dry_run": bool, "request_id": Optional[int], "status": Optional[str], "tables": {...}, "changes": [...], "warnings": [...]}`.

**Transaction shape** (this is the subtle part — read before implementing): a dry run must write *nothing from the bundle* but must still leave a `sync_log` row. So: apply the bundle → build the report dict → **roll back** → add the `SyncLog` row → commit. On a real apply: apply the bundle → set the request fields → add the `SyncLog` row → commit once.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_sync_api_write.py`:

```python
"""Write side: dry run leaves nothing behind, apply commits and delivers, and
neither path ever touches the user table."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_session
from app.main import app
from app.models import Entity, EntityEdge, ResearchRequest, SyncLog, User

HEADERS = {"X-Sync-Token": "s3cret"}

BUNDLE = {
    "entities": [
        {"kind": "company", "eik": "175376051", "name": "Артекс Златен век ООД",
         "founded_year": 2008},
        {"kind": "person", "person_key": "p-1", "name": "Иван Иванов"},
    ],
    "edges": [{"src": {"person_key": "p-1"}, "dst": {"eik": "175376051"},
               "relation": "ownership", "share_pct": 100}],
    "report_md": "# Findings\nArtex litigates through SPVs.",
    "notes": "checked 2026-08-20",
}


@pytest.fixture
def session_and_client(monkeypatch):
    monkeypatch.setenv("RESEARCH_API_TOKEN", "s3cret")
    engine = create_engine("sqlite://", future=True,
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, future=True)()
    s.add_all([
        ResearchRequest(company_name="Артекс", company_eik="175376051",
                        requester_email="a@b.c", status="new"),
        User(email="u@example.com", hashed_password="x", tier="member",
             is_active=True, is_superuser=False, is_verified=True),
    ])
    s.commit()
    app.dependency_overrides[get_session] = lambda: s
    yield s, TestClient(app)
    app.dependency_overrides.pop(get_session, None)
    s.close()


def test_requires_the_token(session_and_client):
    _, client = session_and_client
    r = client.post("/api/admin/sync/requests/1/findings", json=BUNDLE)
    assert r.status_code == 403


def test_dry_run_is_the_default_and_writes_nothing(session_and_client):
    s, client = session_and_client
    body = client.post("/api/admin/sync/requests/1/findings",
                       json=BUNDLE, headers=HEADERS).json()
    assert body["dry_run"] is True
    assert body["tables"]["entity"]["created"] == 2
    assert s.scalar(select(func.count()).select_from(Entity)) == 0
    assert s.get(ResearchRequest, 1).status == "new"
    # ...but the attempt is still logged
    log = s.scalar(select(SyncLog))
    assert log.dry_run is True and log.action == "findings" and log.request_id == 1


def test_apply_writes_rows_and_delivers_the_request(session_and_client):
    s, client = session_and_client
    body = client.post("/api/admin/sync/requests/1/findings?dry_run=false",
                       json=BUNDLE, headers=HEADERS).json()
    assert body["dry_run"] is False and body["status"] == "delivered"
    assert s.scalar(select(func.count()).select_from(Entity)) == 2
    assert s.scalar(select(func.count()).select_from(EntityEdge)) == 1
    req = s.get(ResearchRequest, 1)
    assert req.status == "delivered" and req.delivered_at is not None
    assert req.report_md.startswith("# Findings")
    assert req.notes == "checked 2026-08-20"


def test_applying_twice_is_idempotent(session_and_client):
    s, client = session_and_client
    url = "/api/admin/sync/requests/1/findings?dry_run=false"
    client.post(url, json=BUNDLE, headers=HEADERS)
    second = client.post(url, json=BUNDLE, headers=HEADERS).json()
    assert s.scalar(select(func.count()).select_from(Entity)) == 2
    assert second["tables"]["entity"]["unchanged"] == 2


def test_a_bad_reference_rolls_the_whole_bundle_back(session_and_client):
    s, client = session_and_client
    bad = dict(BUNDLE, edges=[{"src": {"eik": "999999999"},
                               "dst": {"eik": "175376051"}, "relation": "ownership"}])
    r = client.post("/api/admin/sync/requests/1/findings?dry_run=false",
                    json=bad, headers=HEADERS)
    assert r.status_code == 422 and "999999999" in r.json()["detail"]
    assert s.scalar(select(func.count()).select_from(Entity)) == 0  # nothing partial
    assert s.get(ResearchRequest, 1).status == "new"


def test_unattached_bundle_needs_no_request(session_and_client):
    s, client = session_and_client
    body = client.post("/api/admin/sync/bundle?dry_run=false",
                       json=BUNDLE, headers=HEADERS).json()
    assert body["request_id"] is None
    assert s.scalar(select(func.count()).select_from(Entity)) == 2
    assert s.scalar(select(SyncLog)).action == "bundle"


def test_user_table_is_never_touched(session_and_client):
    s, client = session_and_client
    before = s.scalar(select(func.count()).select_from(User))
    client.post("/api/admin/sync/requests/1/findings", json=BUNDLE, headers=HEADERS)
    client.post("/api/admin/sync/requests/1/findings?dry_run=false",
                json=BUNDLE, headers=HEADERS)
    client.post("/api/admin/sync/bundle?dry_run=false", json=BUNDLE, headers=HEADERS)
    assert s.scalar(select(func.count()).select_from(User)) == before == 1
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_sync_api_write.py -v`
Expected: FAIL — 405/404 on the POST routes.

- [ ] **Step 3: Add the write routes to `backend/app/sync/router.py`**

Extend the imports:

```python
from datetime import datetime, timezone

from app.models import SyncLog
from app.sync.schemas import Bundle
from app.sync.upsert import BundleError, apply_bundle
```

Append:

```python
def _run_bundle(session, bundle: Bundle, *, dry_run: bool, action: str,
                req: Optional[ResearchRequest]) -> dict:
    """Apply a bundle and log it.

    A dry run must leave nothing from the bundle behind but must still be
    recorded, so the order is: apply -> capture the report -> roll back -> log.
    A real apply commits the bundle, the request update and the log together.
    """
    try:
        report = apply_bundle(session, bundle)
    except BundleError as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    summary = report.as_dict()

    if dry_run:
        session.rollback()
    else:
        if req is not None:
            if bundle.report_md:
                req.report_md = bundle.report_md
            if bundle.notes:
                req.notes = bundle.notes
            req.status = "delivered"
            req.delivered_at = datetime.now(timezone.utc).replace(tzinfo=None)

    session.add(SyncLog(request_id=req.id if req is not None else None,
                        action=action, dry_run=dry_run, summary=summary))
    session.commit()

    return {"dry_run": dry_run,
            "request_id": req.id if req is not None else None,
            "status": req.status if req is not None else None,
            **summary}


@router.post("/requests/{request_id}/findings")
def push_findings(
    request_id: int,
    bundle: Bundle,
    dry_run: bool = Query(True, description="default true — nothing is written"),
    session=Depends(get_session),
):
    """Apply a findings bundle and mark the request delivered."""
    req = session.get(ResearchRequest, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="unknown request")
    return _run_bundle(session, bundle, dry_run=dry_run, action="findings", req=req)


@router.post("/bundle")
def push_bundle(
    bundle: Bundle,
    dry_run: bool = Query(True, description="default true — nothing is written"),
    session=Depends(get_session),
):
    """Apply a bundle not tied to any request — bulk/crawl data.

    This is what replaces the old ``deploy/ENTITY_PUSH.md`` CSV mirror.
    """
    return _run_bundle(session, bundle, dry_run=dry_run, action="bundle", req=None)
```

Note on the dry-run rollback: `req` is expired by `session.rollback()`, but the dry-run branch never modified it, so reading `req.status` afterwards re-loads the unchanged row. That is intentional — the response reports the *current* status.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_sync_api_write.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Run the entire suite**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: PASS — everything, including all pre-existing tests.

- [ ] **Step 6: Commit**

```bash
git add backend/app/sync/router.py backend/tests/test_sync_api_write.py
git commit -m "feat(sync): findings and bulk bundle endpoints, dry-run by default

Dry run applies, reports, then rolls back — and still writes a sync_log row so
every attempt is auditable.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 9: `scripts/pb.py` — the MacBook client

**Files:**
- Create: `scripts/pb.py`
- Modify: `.env.example` (document the two new variables)
- Test: `backend/tests/test_pb_cli.py`

**Interfaces:**
- Consumes: the HTTP API from Tasks 7-8.
- Produces: `pb.load_env(path) -> dict`, `pb.format_report(body: dict) -> str`, `pb.main(argv: list[str]) -> int`.

The tunnel and the network calls are not unit-tested (no network in tests); the pure pieces — env loading and report formatting — are.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_pb_cli.py`:

```python
"""Pure parts of the pb client: env parsing and the human-readable diff."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import pb  # noqa: E402


def test_load_env_parses_and_ignores_comments(tmp_path):
    f = tmp_path / ".env"
    f.write_text("# comment\nRESEARCH_API_TOKEN=abc123\n\nexport VPS_HOST=example.com\n")
    env = pb.load_env(f)
    assert env["RESEARCH_API_TOKEN"] == "abc123"
    assert env["VPS_HOST"] == "example.com"


def test_load_env_strips_quotes(tmp_path):
    f = tmp_path / ".env"
    f.write_text('RESEARCH_API_TOKEN="quoted"\n')
    assert pb.load_env(f)["RESEARCH_API_TOKEN"] == "quoted"


def test_format_report_marks_a_dry_run_and_lists_changes():
    out = pb.format_report({
        "dry_run": True, "request_id": 7, "status": "new",
        "tables": {"entity": {"created": 2, "updated": 1, "unchanged": 0, "skipped": 0}},
        "changes": [{"table": "entity", "key": "175376051", "field": "founded_year",
                     "from": None, "to": 2008}],
        "warnings": ["heads up"],
    })
    assert "DRY RUN" in out and "nothing was written" in out
    assert "entity" in out and "created 2" in out
    assert "founded_year" in out and "2008" in out
    assert "heads up" in out


def test_format_report_marks_an_applied_push():
    out = pb.format_report({"dry_run": False, "request_id": 7, "status": "delivered",
                            "tables": {}, "changes": [], "warnings": []})
    assert "APPLIED" in out and "delivered" in out


def test_format_report_never_prints_the_token():
    out = pb.format_report({"dry_run": True, "request_id": None, "status": None,
                            "tables": {}, "changes": [], "warnings": []})
    assert "TOKEN" not in out.upper()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_pb_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pb'`

- [ ] **Step 3: Write `scripts/pb.py`**

```python
#!/usr/bin/env python3
"""pb — push research findings from this machine into production.

The sync endpoints are not reachable from the internet: nginx refuses
``/api/admin/sync/`` and this client opens its own SSH tunnel to uvicorn on the
VPS for the duration of a command. The token is a second factor, not the only
one.

Standard library only, by design — nothing gets installed on this machine.

    pb requests [--status new]          what is waiting
    pb claim 7                          new -> in_progress
    pb prod 175376051 204741372         what production already holds
    pb push 7 bundle.json               DRY RUN, prints the diff
    pb push 7 bundle.json --apply       commits
    pb push-bulk bundle.json [--apply]  bundle not tied to a request

Reads RESEARCH_API_TOKEN and VPS_HOST/VPS_USER/VPS_PORT from the repo .env.
Never prints the token or the host.
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_PORT = 8787
REMOTE_PORT = 8000
TUNNEL_TIMEOUT = 15.0


def load_env(path: Path) -> dict:
    """Minimal .env reader — KEY=value, ignoring blanks, comments and `export`."""
    env = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


class Tunnel:
    """SSH port-forward held open for the duration of one command."""

    def __init__(self, env: dict):
        self.host = env.get("VPS_HOST", "app.example.com")
        self.user = env.get("VPS_USER", "mvp")
        self.port = env.get("VPS_PORT", "22")
        self.proc: Optional[subprocess.Popen] = None

    def __enter__(self) -> str:
        self.proc = subprocess.Popen(
            ["ssh", "-N", "-p", self.port,
             "-L", f"{LOCAL_PORT}:127.0.0.1:{REMOTE_PORT}",
             f"{self.user}@{self.host}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        deadline = time.time() + TUNNEL_TIMEOUT
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise SystemExit("ssh tunnel failed to start — check your SSH access")
            with socket.socket() as sock:
                sock.settimeout(0.3)
                if sock.connect_ex(("127.0.0.1", LOCAL_PORT)) == 0:
                    return f"http://127.0.0.1:{LOCAL_PORT}"
            time.sleep(0.3)
        self.__exit__(None, None, None)
        raise SystemExit("ssh tunnel did not come up within 15s")

    def __exit__(self, *exc) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            self.proc.wait(timeout=5)


def call(base: str, token: str, method: str, path: str,
         params: Optional[list] = None, body: Optional[dict] = None) -> dict:
    url = base + path + (("?" + urllib.parse.urlencode(params)) if params else "")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-Sync-Token", token)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read() or "null")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise SystemExit(f"HTTP {exc.code}: {detail}")


def format_report(body: dict) -> str:
    """Human-readable push result. Never includes credentials."""
    head = "DRY RUN — nothing was written" if body["dry_run"] else "APPLIED"
    lines = [head]
    if body.get("request_id") is not None:
        lines.append(f"request {body['request_id']} -> status {body.get('status')}")
    for table, stat in sorted(body.get("tables", {}).items()):
        lines.append(
            f"  {table:<16} created {stat['created']}  updated {stat['updated']}"
            f"  unchanged {stat['unchanged']}  skipped {stat['skipped']}"
        )
    changes = body.get("changes") or []
    if changes:
        lines.append("  changes:")
        for c in changes:
            lines.append(f"    {c['table']} {c['key']}: {c['field']} "
                         f"{c['from']!r} -> {c['to']!r}")
    for w in body.get("warnings") or []:
        lines.append(f"  ! {w}")
    return "\n".join(lines)


def format_requests(rows: list) -> str:
    if not rows:
        return "nothing waiting"
    out = []
    for r in rows:
        checked = r.get("court_checked_at") or "never"
        out.append(
            f"#{r['id']:<4} {r['status']:<12} {r['order_type']:<15} "
            f"{(r['company_eik'] or '—'):<11} {r['company_name'][:34]:<34} "
            f"in_db={'y' if r['in_db'] else 'n'} court={checked}"
        )
    return "\n".join(out)


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(prog="pb", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("requests", help="list research requests")
    p.add_argument("--status", default="new")

    p = sub.add_parser("claim", help="mark a request in_progress")
    p.add_argument("request_id", type=int)

    p = sub.add_parser("prod", help="what production holds for these ЕИКs")
    p.add_argument("eik", nargs="+")

    p = sub.add_parser("push", help="push findings for a request")
    p.add_argument("request_id", type=int)
    p.add_argument("bundle", type=Path)
    p.add_argument("--apply", action="store_true", help="commit (default: dry run)")

    p = sub.add_parser("push-bulk", help="push a bundle not tied to a request")
    p.add_argument("bundle", type=Path)
    p.add_argument("--apply", action="store_true")

    args = parser.parse_args(argv)

    env = load_env(REPO_ROOT / ".env")
    token = env.get("RESEARCH_API_TOKEN")
    if not token:
        raise SystemExit("RESEARCH_API_TOKEN is not set in .env")

    with Tunnel(env) as base:
        if args.cmd == "requests":
            print(format_requests(
                call(base, token, "GET", "/api/admin/sync/requests",
                     params=[("status", args.status)])))
        elif args.cmd == "claim":
            body = call(base, token, "POST",
                        f"/api/admin/sync/requests/{args.request_id}/claim")
            print(f"request {body['id']} -> {body['status']}")
        elif args.cmd == "prod":
            body = call(base, token, "GET", "/api/admin/sync/entities",
                        params=[("eik", e) for e in args.eik])
            print(json.dumps(body, indent=2, ensure_ascii=False))
        elif args.cmd in ("push", "push-bulk"):
            bundle = json.loads(args.bundle.read_text())
            params = [("dry_run", "false" if args.apply else "true")]
            path = ("/api/admin/sync/bundle" if args.cmd == "push-bulk"
                    else f"/api/admin/sync/requests/{args.request_id}/findings")
            print(format_report(
                call(base, token, "POST", path, params=params, body=bundle)))
            if not args.apply:
                print("\nre-run with --apply to commit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Make it executable and document the env vars**

```bash
chmod +x scripts/pb.py
```

Append to `.env.example`:

```
# Research sync API (scripts/pb.py -> production). The token must match
# RESEARCH_API_TOKEN in /home/deploy/secrets/pocketbroker.env on the VPS.
RESEARCH_API_TOKEN=
VPS_HOST=
VPS_USER=deploy
VPS_PORT=22
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_pb_cli.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Check the CLI's help works**

Run: `python3 scripts/pb.py --help && python3 scripts/pb.py push --help`
Expected: usage text, exit 0. (No network is touched by `--help`.)

- [ ] **Step 7: Commit**

```bash
git add scripts/pb.py .env.example backend/tests/test_pb_cli.py
git commit -m "feat(sync): pb client — stdlib-only CLI over an SSH tunnel

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 10: Deploy documentation and retiring ENTITY_PUSH

**Files:**
- Create: `deploy/SYNC_API.md`
- Modify: `deploy/ENTITY_PUSH.md` (deprecation banner)
- Modify: `RUNBOOK.md` (sync section)
- Modify: `CLAUDE.md` (known-issues row)

**Interfaces:**
- Consumes: everything above.
- Produces: no code.

- [ ] **Step 1: Write `deploy/SYNC_API.md`**

```markdown
# Research Sync API — MacBook → production

Replaces the CSV + `scp` + VPS-Claude procedure in `ENTITY_PUSH.md`. Findings
are pushed straight into the production database over an SSH tunnel.

## One-time setup

### 1. Generate and install the token (on the VPS)

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Add the value to `/home/deploy/secrets/pocketbroker.env` as `RESEARCH_API_TOKEN=…`
and restart the service:

```bash
sudo systemctl restart pocketbroker-api
```

Put the **same** value in the local repo `.env` as `RESEARCH_API_TOKEN`, plus
`VPS_HOST`, `VPS_USER`, `VPS_PORT`.

### 2. Close the route to the internet (on the VPS)

In the nginx server block for the site, **above** the general `/api/` location:

```nginx
location /api/admin/sync/ {
    deny all;
}
```

Then `sudo nginx -t && sudo systemctl reload nginx`.

Verify from the MacBook — this must return 403 from nginx, not a JSON error:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://app.example.com/api/admin/sync/requests
# 403
```

`pb` does not go through nginx: it tunnels to uvicorn on 127.0.0.1:8000.

### 3. Migrate the schema

`deploy.sh` runs `alembic upgrade head`, which applies `b3c4d5e6f7a8`
(`sync_log` + the `research_request` delivery columns).

## Daily use

```bash
python3 scripts/pb.py requests              # what is waiting
python3 scripts/pb.py claim 7               # new -> in_progress
python3 scripts/pb.py prod 175376051        # what prod already holds
python3 scripts/pb.py push 7 data/bundles/175376051_20260820.json
python3 scripts/pb.py push 7 data/bundles/175376051_20260820.json --apply
```

`push` is a **dry run** unless `--apply` is given: the server applies the bundle
in a transaction, reports every field it would change, and rolls back.

## Bundle format

See §6 of `docs/superpowers/specs/2026-08-20-research-sync-api-design.md`.
Entities are addressed by ЕИК (companies) or `person_key` (persons) — never by
database id. Capital crosses as `capital_eur`.

Bundles are written to `data/bundles/<eik>_<stamp>.json` and are the record of
what was delivered; re-pushing one is a no-op.

## Safety properties

- The sync endpoints never read or write `user` or `oauth_account`.
- An unset `RESEARCH_API_TOKEN` rejects every request (fails closed).
- A bundle is all-or-nothing: an unresolvable reference returns 422 and writes
  nothing.
- Every push, dry runs included, appends a row to `sync_log`.
```

- [ ] **Step 2: Deprecate `deploy/ENTITY_PUSH.md`**

Insert directly under the H1:

```markdown
> ## ⛔️ DEPRECATED — do not run this
>
> Production is now written directly by the sync API (`deploy/SYNC_API.md`).
> The procedure below **full-mirrors** the entity tables from local: it runs
> `DELETE FROM entity` and reloads from CSV, which would **erase every finding
> pushed through the API** since the last local scrape.
>
> Use `python3 scripts/pb.py push-bulk <bundle.json>` for bulk data instead.
>
> Kept only as a record of the pre-API procedure.
```

- [ ] **Step 3: Add a sync section to `RUNBOOK.md`**

Append:

```markdown
## Pushing research findings to production

Full procedure: `deploy/SYNC_API.md`.

```bash
python3 scripts/pb.py requests                    # what is waiting
python3 scripts/pb.py claim <id>                  # mark in_progress
python3 scripts/pb.py prod <eik>                  # what prod already holds
python3 scripts/pb.py push <id> <bundle.json>     # dry run — prints the diff
python3 scripts/pb.py push <id> <bundle.json> --apply
```

Bundles live in `data/bundles/<eik>_<stamp>.json`. `deploy/ENTITY_PUSH.md` is
deprecated — running it would erase API-written findings.
```

- [ ] **Step 4: Update the known-issues table in `CLAUDE.md`**

Add a row:

```markdown
| `deploy/ENTITY_PUSH.md` is destructive | Deprecated | Full-mirrors entity tables; would erase API-written findings. Use `scripts/pb.py` — see `deploy/SYNC_API.md` |
```

- [ ] **Step 5: Verify the whole suite one more time**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: PASS, no failures, no errors.

- [ ] **Step 6: Commit**

```bash
git add deploy/SYNC_API.md deploy/ENTITY_PUSH.md RUNBOOK.md CLAUDE.md
git commit -m "docs(sync): deploy guide for the sync API, deprecate ENTITY_PUSH

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Human steps (cannot be automated from here)

After the tasks are complete, the following need hands on the VPS — they are
detailed in `deploy/SYNC_API.md`:

1. Generate `RESEARCH_API_TOKEN`, add it to `/home/deploy/secrets/pocketbroker.env`
   and to the local `.env`, restart `pocketbroker-api`.
2. Add the nginx `deny all` block for `/api/admin/sync/` and reload nginx.
3. Run `deploy.sh` so `alembic upgrade head` applies `b3c4d5e6f7a8`.
4. Smoke test: `python3 scripts/pb.py requests`, then a dry-run push.
5. `git push` — the branch is never pushed automatically.

## Verification checklist

- [ ] `cd backend && .venv/bin/python -m pytest -q` passes, including every
      pre-existing test
- [ ] `.venv/bin/alembic upgrade head` then `downgrade -1` then `upgrade head`
      round-trips cleanly
- [ ] `curl https://app.example.com/api/admin/sync/requests` returns
      403 from nginx
- [ ] A dry-run push against a real production request leaves the row count
      unchanged and the request still `new`
- [ ] The same push with `--apply` delivers it, and re-running reports
      everything `unchanged`
- [ ] Production `user` count is identical before and after
