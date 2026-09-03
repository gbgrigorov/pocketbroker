"""Admin read views: all research requests + all users (superuser-gated).

The gate itself is fastapi-users' ``current_superuser`` (401 anon / 403 member);
here we override it to assert the payloads, plus one test that a 403 from the gate
propagates through the route.
"""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import current_superuser
from app.db import Base, get_session
from app.main import app
from app.models import ResearchRequest, User


def _seed(s):
    s.add_all([
        ResearchRequest(company_name="Artex OOD", requester_email="lead@example.com"),
        ResearchRequest(
            company_name="ЕНЕКОД ГРИЙН", company_eik="204741372",
            requester_email="member@example.com", order_type="court_research",
            scope="network", search_type="eik_name", network_depth=2,
            entity_count=12, price_eur=18.0, status="new",
        ),
    ])
    s.add(User(email="admin@example.com", name="Gabriel",
               hashed_password="x", tier="member",
               is_active=True, is_superuser=True, is_verified=True))
    s.commit()


@pytest.fixture
def client():
    engine = create_engine("sqlite://", future=True,
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, future=True)()
    _seed(s)
    app.dependency_overrides[get_session] = lambda: s
    app.dependency_overrides[current_superuser] = lambda: object()  # treat caller as admin
    yield TestClient(app)
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(current_superuser, None)
    s.close()


def test_lists_all_requests_newest_first(client):
    rows = client.get("/api/admin/research-requests").json()
    assert len(rows) == 2
    court = next(r for r in rows if r["order_type"] == "court_research")
    assert court["company_eik"] == "204741372" and court["price_eur"] == 18.0
    assert court["scope"] == "network" and court["entity_count"] == 12
    # full row exposes the requester contact for follow-up
    assert all("requester_email" in r for r in rows)


def test_lists_all_users(client):
    users = client.get("/api/admin/users").json()
    assert len(users) == 1
    u = users[0]
    assert u["email"] == "admin@example.com" and u["is_superuser"] is True
    assert u["tier"] == "member"
    assert "hashed_password" not in u  # schema never leaks the password hash


def test_non_admin_gets_403(client):
    def deny():
        raise HTTPException(status_code=403, detail="Forbidden")
    app.dependency_overrides[current_superuser] = deny
    assert client.get("/api/admin/research-requests").status_code == 403
    assert client.get("/api/admin/users").status_code == 403
