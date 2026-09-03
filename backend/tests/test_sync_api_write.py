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


def test_apply_clears_the_read_caches(session_and_client, monkeypatch):
    """A push that does not invalidate the caches is invisible in search.

    /entities, /map and /cities are served from module-level dicts, so writing
    rows is not enough — the caches have to be dropped or the new company simply
    does not appear until someone restarts the service.
    """
    import app.routes as routes
    s, client = session_and_client
    routes._entities_cache = [{"stale": True}]
    routes._map_cache["__all__"] = [{"stale": True}]

    client.post("/api/admin/sync/bundle", json=BUNDLE, headers=HEADERS)      # dry run
    assert routes._entities_cache is not None, "a dry run must not disturb the caches"

    client.post("/api/admin/sync/bundle?dry_run=false", json=BUNDLE, headers=HEADERS)
    assert routes._entities_cache is None
    assert routes._map_cache == {}
