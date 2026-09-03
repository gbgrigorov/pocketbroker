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
