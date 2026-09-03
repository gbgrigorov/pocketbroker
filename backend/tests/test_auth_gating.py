"""Login gating: anonymous viewers see public facts only; people + research
(owners/managers/network/signals) are stripped server-side, and the network/graph
endpoints 401. Members (logged-in) see everything.

Auth state is simulated by overriding ``current_user_optional`` — anonymous = ``None``,
member = a stand-in user. The real fastapi-users login/Google flow is verified manually
(it needs the async auth DB), not here.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import current_user_optional
from app.db import Base, get_session
from app.main import app
from app.models import Entity, EntitySignal
from etl.entities import OwnershipReport, load_ownership
from etl.load_phase3 import Phase3Report, load_builders
from tests.conftest import Member

BUILDERS = [{"eik": "B1", "name": "СТРОЙ ЕДНО ООД"}]
OWNERSHIP = [
    {"eik": "B1", "name": "СТРОЙ ЕДНО ООД", "source": "papagal", "related": [
        {"kind": "person", "name": "ИВАН ПЕТРОВ", "person_key": "P",
         "relation": "ownership", "role": "Съдружник", "direction": "in",
         "is_current": True},
    ]},
]


@pytest.fixture
def session():
    engine = create_engine("sqlite://", future=True,
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, future=True)()
    load_builders(s, BUILDERS, Phase3Report())
    load_ownership(s, OWNERSHIP, OwnershipReport())
    s.commit()
    # One official signal about B1, so research-gating is observable (member sees 1, anon 0).
    b1 = s.scalar(select(Entity).where(Entity.eik == "B1"))
    s.add(EntitySignal(
        entity_id=b1.id, subject_kind="company", matched_name="СТРОЙ ЕДНО ООД",
        source_type="registry", tier="official", match_confidence="eik",
        title="Insolvency case", url="https://example.com/case/1",
    ))
    s.commit()
    app.dependency_overrides[get_session] = lambda: s
    yield s
    app.dependency_overrides.clear()


def anon_client():
    app.dependency_overrides[current_user_optional] = lambda: None
    return TestClient(app)


def member_client():
    app.dependency_overrides[current_user_optional] = lambda: Member()
    return TestClient(app)


LOCKED_KEYS = ["owners", "managers", "owns", "manages", "signals", "signal_counts",
               "insolvency_flag", "tax_debt_bgn"]


# --- entity profile ---------------------------------------------------------

def test_anon_entity_profile_strips_people_and_research(session):
    data = anon_client().get("/api/entities/B1").json()
    # Public facts survive.
    assert data["name"] == "СТРОЙ ЕДНО ООД"
    assert data["eik"] == "B1"
    # Locked groups removed, and flagged so the UI can show a sign-in CTA.
    for key in LOCKED_KEYS:
        assert key not in data, f"{key} should be stripped for anonymous"
    assert set(data["locked"]) == {"people", "research"}


def test_member_entity_profile_is_full(session):
    data = member_client().get("/api/entities/B1").json()
    assert any(o["name"] == "ИВАН ПЕТРОВ" for o in data["owners"])
    assert data["signal_counts"]["official"] == 1
    assert "locked" not in data


# --- builder profile --------------------------------------------------------

def test_anon_builder_profile_strips_owners(session):
    data = anon_client().get("/api/builders/B1").json()
    assert data["eik"] == "B1" and data["name"] == "СТРОЙ ЕДНО ООД"
    assert "owners" not in data and "managers" not in data
    assert "people" in data["locked"]


# --- network / graph: 401 for anon, 200 for member --------------------------

@pytest.mark.parametrize("path", ["/api/entities/B1/network", "/api/builders/B1/network",
                                  "/api/graph"])
def test_anon_network_and_graph_401(session, path):
    assert anon_client().get(path).status_code == 401


@pytest.mark.parametrize("path", ["/api/entities/B1/network", "/api/builders/B1/network",
                                  "/api/graph"])
def test_member_network_and_graph_ok(session, path):
    r = member_client().get(path)
    assert r.status_code == 200
    assert "nodes" in r.json()


# --- entity list: research (caution counts) zeroed for anon -----------------

def test_anon_list_zeros_signal_counts(session):
    items = anon_client().get("/api/entities").json()["items"]
    b1 = next(i for i in items if i["eik"] == "B1")
    assert b1["name"] == "СТРОЙ ЕДНО ООД"          # public facts still listed
    assert b1["signal_counts"] == {"official": 0, "community": 0, "web": 0}


def test_member_list_shows_signal_counts(session):
    items = member_client().get("/api/entities").json()["items"]
    b1 = next(i for i in items if i["eik"] == "B1")
    assert b1["signal_counts"]["official"] == 1
