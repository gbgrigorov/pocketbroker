"""Admin inbox coverage flags: "network" + "court checked".

The load-bearing case is the **zero-result court search**. A search that finds no
acts writes no ``entity_signal`` row, so deriving "checked" from signal presence
would report every clean company as unchecked. These tests pin the distinction
between *checked, nothing found* and *never checked*.
"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import current_superuser
from app.db import Base, get_session
from app.main import app
from app.models import CourtCheck, Entity, EntityEdge, ResearchRequest

CHECKED = datetime(2026, 8, 4, 18, 0, 0)
EARLIER = datetime(2026, 6, 19, 12, 0, 0)


def _seed(s):
    # 1. in DB + court-checked, acts found
    hit = Entity(kind="company", name="НЕРА", eik="120553098", slug="nera")
    # 2. in DB + court-checked, NOTHING found  <- must still read as checked
    clean = Entity(kind="company", name="ДАМЯНОВ", eik="147024297", slug="damyanov")
    # 3. in DB, never court-checked
    unchecked = Entity(kind="company", name="КОРУМ", eik="205137389", slug="korum")
    person = Entity(kind="person", name="Тест Лице", person_key="abc-1", slug="test-litse")
    s.add_all([hit, clean, unchecked, person])
    s.flush()

    s.add_all([
        EntityEdge(src_entity_id=person.id, dst_entity_id=hit.id,
                   relation="manages", role="Управител"),
        EntityEdge(src_entity_id=person.id, dst_entity_id=clean.id,
                   relation="manages", role="Управител"),
    ])
    s.add_all([
        CourtCheck(eik="120553098", name="НЕРА", method="eik",
                   acts_found=8, checked_at=CHECKED),
        CourtCheck(eik="147024297", name="ДАМЯНОВ", method="eik",
                   acts_found=0, checked_at=CHECKED),
        # An older run on the same ЕИК — the newest check must win.
        CourtCheck(eik="120553098", name="НЕРА", method="eik",
                   acts_found=2, checked_at=EARLIER),
    ])
    s.add_all([
        ResearchRequest(company_name="НЕРА ЕООД", company_eik="120553098",
                        requester_email="a@example.com"),
        ResearchRequest(company_name="Дамянов оод", company_eik="147024297",
                        requester_email="b@example.com"),
        ResearchRequest(company_name="корум еоод", company_eik="205137389",
                        requester_email="c@example.com"),
        ResearchRequest(company_name="Ново ЕООД", company_eik="999999999",
                        requester_email="d@example.com"),
        ResearchRequest(company_name="Стройинвест", requester_email="e@example.com"),
    ])
    s.commit()


@pytest.fixture
def rows():
    engine = create_engine("sqlite://", future=True,
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, future=True)()
    _seed(s)
    app.dependency_overrides[get_session] = lambda: s
    app.dependency_overrides[current_superuser] = lambda: object()
    client = TestClient(app)
    data = {r["company_name"]: r for r in client.get("/api/admin/research-requests").json()}
    yield data
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(current_superuser, None)
    s.close()


def test_zero_result_search_still_counts_as_checked(rows):
    """The whole reason court_check exists: clean != unchecked."""
    r = rows["Дамянов оод"]
    assert r["court_checked_at"] is not None
    assert r["court_acts"] == 0


def test_never_searched_is_distinguishable_from_clean(rows):
    r = rows["корум еоод"]
    assert r["court_checked_at"] is None
    assert r["court_acts"] is None
    assert r["in_db"] is True  # in the DB, just never court-checked


def test_latest_check_wins(rows):
    r = rows["НЕРА ЕООД"]
    assert r["court_checked_at"].startswith("2026-08-04")
    assert r["court_acts"] == 8  # not the older run's 2


def test_network_flag_tracks_entity_presence(rows):
    assert rows["НЕРА ЕООД"]["in_db"] is True
    assert rows["НЕРА ЕООД"]["edge_count"] == 1
    assert rows["Ново ЕООД"]["in_db"] is False   # ЕИК given, no entity
    assert rows["Стройинвест"]["in_db"] is False  # no ЕИК at all


def test_request_without_eik_has_no_court_data(rows):
    r = rows["Стройинвест"]
    assert r["court_checked_at"] is None and r["entity_id"] is None


# --- court_check loader ------------------------------------------------------


def _session():
    engine = create_engine("sqlite://", future=True,
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def test_loader_is_idempotent_and_keeps_zero_results():
    from etl.load_court_checks import CheckReport, load_checks

    s = _session()
    rows = [
        {"eik": "120553098", "name": "НЕРА", "acts_found": 8,
         "checked_at": "2026-08-04T18:00:00"},
        {"eik": "147024297", "name": "ДАМЯНОВ", "acts_found": 0,
         "checked_at": "2026-08-04T18:00:00"},
    ]
    r1 = CheckReport()
    load_checks(s, rows, r1)
    s.commit()
    assert r1.checks_loaded == 2

    # Same file again -> nothing new, the zero-result row included.
    r2 = CheckReport()
    load_checks(s, rows, r2)
    s.commit()
    assert (r2.checks_loaded, r2.skipped_existing) == (0, 2)
    assert s.query(CourtCheck).filter_by(eik="147024297").one().acts_found == 0

    # A later run on the same ЕИК is a new event, not a duplicate.
    r3 = CheckReport()
    load_checks(s, [{"eik": "147024297", "acts_found": 1,
                     "checked_at": "2026-09-01T09:00:00"}], r3)
    s.commit()
    assert r3.checks_loaded == 1
    assert s.query(CourtCheck).filter_by(eik="147024297").count() == 2
    s.close()


def test_loader_rejects_rows_without_eik_or_timestamp():
    from etl.load_court_checks import CheckReport, load_checks

    s = _session()
    report = CheckReport()
    load_checks(s, [
        {"eik": "", "checked_at": "2026-08-04T18:00:00"},
        {"eik": "120553098"},
        {"eik": "120553098", "checked_at": "not-a-date"},
    ], report)
    s.commit()
    assert (report.checks_loaded, report.skipped_invalid) == (0, 3)
    s.close()
