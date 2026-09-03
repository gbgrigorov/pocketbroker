"""The запор flag: pushed through the sync API, gated like the rest of research.

A запор (attachment on a partner's share) is registered in the Търговски регистър
and never surfaces in legalacts.justice.bg, so it needs to be carried explicitly
rather than inferred from court data.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import current_user_optional
from app.db import Base, get_session
from app.main import app
from app.models import Entity
from app.sync.schemas import Bundle
from app.sync.upsert import apply_bundle

HEADERS = {"X-Sync-Token": "s3cret"}
URL = "https://portal.registryagency.bg/CR/en/Reports/ActiveConditionTabResult?uic=203879071"

FLAGGED = {"kind": "company", "eik": "203879071", "name": "Смарт Хаус Къмпани",
           "has_seizure": True, "seizure_count": 2, "seizure_last_at": "2024-02-09",
           "seizure_source_url": URL}


@pytest.fixture
def session():
    engine = create_engine("sqlite://", future=True,
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, future=True)()
    yield s
    s.close()


def test_seizure_fields_are_written(session):
    apply_bundle(session, Bundle(entities=[FLAGGED]))
    e = session.scalar(select(Entity).where(Entity.eik == "203879071"))
    assert e.has_seizure is True
    assert e.seizure_count == 2
    assert e.seizure_last_at.isoformat() == "2024-02-09"
    assert e.seizure_source_url == URL


def test_a_lifted_seizure_can_be_cleared(session):
    """enrich-don't-erase skips None, not False — otherwise a lifted attachment
    could never be turned off and the red flag would be permanent."""
    apply_bundle(session, Bundle(entities=[FLAGGED]))
    apply_bundle(session, Bundle(entities=[dict(FLAGGED, has_seizure=False,
                                                seizure_count=0)]))
    e = session.scalar(select(Entity).where(Entity.eik == "203879071"))
    assert e.has_seizure is False and e.seizure_count == 0


def test_omitting_the_fields_leaves_the_flag_alone(session):
    apply_bundle(session, Bundle(entities=[FLAGGED]))
    apply_bundle(session, Bundle(entities=[{"kind": "company", "eik": "203879071",
                                            "name": "Смарт Хаус Къмпани"}]))
    e = session.scalar(select(Entity).where(Entity.eik == "203879071"))
    assert e.has_seizure is True, "a partial push must not silently clear the flag"


def test_default_is_not_flagged(session):
    apply_bundle(session, Bundle(entities=[{"kind": "company", "eik": "111222333",
                                            "name": "X"}]))
    e = session.scalar(select(Entity).where(Entity.eik == "111222333"))
    assert e.has_seizure is False and e.seizure_count == 0


@pytest.fixture
def client(session, monkeypatch):
    monkeypatch.setenv("RESEARCH_API_TOKEN", "s3cret")
    apply_bundle(session, Bundle(entities=[FLAGGED]))
    session.commit()
    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.pop(get_session, None)


def test_entity_detail_exposes_the_flag_when_logged_in(client):
    body = client.get("/api/entities/203879071").json()
    assert body["has_seizure"] is True
    assert body["seizure_count"] == 2
    assert body["seizure_last_at"] == "2024-02-09"
    assert body["seizure_source_url"] == URL


def test_anonymous_viewers_do_not_see_the_flag(client):
    # conftest logs every test in as a member; opt back out to check the gate.
    app.dependency_overrides[current_user_optional] = lambda: None
    try:
        body = client.get("/api/entities/203879071").json()
        assert "has_seizure" not in body
        assert "seizure_source_url" not in body
        assert "research" in body["locked"]
    finally:
        app.dependency_overrides.pop(current_user_optional, None)
