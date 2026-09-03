"""Phase-3.5 entity-wide API: search / profile / network across ALL graph nodes,
not just the 134 licensed builders.

Regression that motivated this: a developer company (БИЛД ИНВЕСТ БЪЛГАРИЯ, ЕИК
203539318) exists in the graph but was unsearchable because search was builder-only.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_session
from app.main import app
from app.models import City
from etl.entities import OwnershipReport, load_ownership
from etl.load_phase3 import Phase3Report, load_builders

# Licensed builders.
BUILDERS = [{"eik": "B1", "name": "СТРОЙ ЕДНО ООД"}, {"eik": "B2", "name": "СТРОЙ ДВЕ ООД"}]

# Edges (related direction "in" = the related entity owns/manages the top-level eik):
#   ИВАН(P)  owns B1, B2          ХОЛДИНГ(C) owns B1        ГЕОРГИ(P2) owns C and БИЛД ИНВЕСТ
# So C is bidirectional: owner=ГЕОРГИ (incoming), owns=B1 (outgoing).
# БИЛД ИНВЕСТ is a *non-builder* company — the regression case.
OWNERSHIP = [
    {"eik": "B1", "name": "СТРОЙ ЕДНО ООД", "source": "papagal", "related": [
        {"kind": "person", "name": "ИВАН ПЕТРОВ", "person_key": "P",
         "relation": "ownership", "role": "Съдружник", "direction": "in", "is_current": True},
        {"kind": "company", "name": "ХОЛДИНГ АД", "eik": "C",
         "relation": "ownership", "role": "Съдружник", "direction": "in", "is_current": True},
    ]},
    {"eik": "B2", "name": "СТРОЙ ДВЕ ООД", "source": "papagal", "related": [
        {"kind": "person", "name": "ИВАН ПЕТРОВ", "person_key": "P",
         "relation": "ownership", "role": "Едноличен собственик", "direction": "in",
         "is_current": True},
    ]},
    {"eik": "C", "name": "ХОЛДИНГ АД", "source": "papagal", "related": [
        {"kind": "person", "name": "ГЕОРГИ ДИМОВ", "person_key": "P2",
         "relation": "ownership", "role": "Едноличен собственик", "direction": "in",
         "is_current": True},
    ]},
    {"eik": "203539318", "name": "БИЛД ИНВЕСТ БЪЛГАРИЯ АД", "source": "papagal", "related": [
        {"kind": "person", "name": "ГЕОРГИ ДИМОВ", "person_key": "P2",
         "relation": "ownership", "role": "Едноличен собственик", "direction": "in",
         "is_current": True},
    ]},
]


@pytest.fixture
def client():
    engine = create_engine("sqlite://", future=True,
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, future=True)()
    s.add(City(name="София", slug="sofia"))
    s.commit()
    load_builders(s, BUILDERS, Phase3Report())
    load_ownership(s, OWNERSHIP, OwnershipReport())
    s.commit()
    app.dependency_overrides[get_session] = lambda: s
    yield TestClient(app)
    app.dependency_overrides.clear()
    s.close()


# --- search ----------------------------------------------------------------

def test_search_finds_non_builder_company_by_name(client):
    """The original bug: БИЛД ИНВЕСТ (a developer, not a КСБ builder) is findable."""
    items = client.get("/api/entities?q=БИЛД ИНВЕСТ").json()["items"]
    hit = next(i for i in items if i["eik"] == "203539318")
    assert hit["kind"] == "company"
    assert hit["is_builder"] is False
    assert hit["degree"] >= 1


def test_search_by_eik(client):
    items = client.get("/api/entities?q=203539318").json()["items"]
    assert any(i["eik"] == "203539318" for i in items)


def test_search_finds_person(client):
    items = client.get("/api/entities?q=ИВАН").json()["items"]
    ivan = next(i for i in items if i["name"] == "ИВАН ПЕТРОВ")
    assert ivan["kind"] == "person"
    assert ivan["degree"] == 2  # owns B1 and B2


def test_search_builders_first(client):
    items = client.get("/api/entities?q=СТРОЙ").json()["items"]
    assert {i["eik"] for i in items} == {"B1", "B2"}
    assert all(i["is_builder"] for i in items)


def test_kind_filter(client):
    people = client.get("/api/entities?kind=person").json()["items"]
    assert people and all(i["kind"] == "person" for i in people)
    builders = client.get("/api/entities?kind=builder").json()["items"]
    assert builders and all(i["is_builder"] for i in builders)


# --- profile (bidirectional) -----------------------------------------------

def test_company_profile_is_bidirectional(client):
    """ХОЛДИНГ is owned by ГЕОРГИ (incoming) AND owns СТРОЙ ЕДНО (outgoing)."""
    data = client.get("/api/entities/C").json()
    assert data["kind"] == "company"
    assert any(o["name"] == "ГЕОРГИ ДИМОВ" for o in data["owners"])
    assert any(o["eik"] == "B1" for o in data["owns"])


def test_person_profile_lists_holdings(client):
    data = client.get("/api/entities/P").json()
    assert data["kind"] == "person"
    owned = {o["eik"] for o in data["owns"]}
    assert {"B1", "B2"} <= owned


def test_builder_profile_keeps_builder_extras(client):
    data = client.get("/api/entities/B1").json()
    assert data["is_builder"] is True
    assert "projects" in data


def test_unknown_entity_404(client):
    assert client.get("/api/entities/ZZZ").status_code == 404


# --- network ----------------------------------------------------------------

def test_network_by_eik(client):
    data = client.get("/api/entities/203539318/network?depth=1").json()
    names = {n["name"] for n in data["nodes"]}
    assert "БИЛД ИНВЕСТ БЪЛГАРИЯ АД" in names
    assert "ГЕОРГИ ДИМОВ" in names


def test_network_by_person_key(client):
    data = client.get("/api/entities/P/network?depth=1").json()
    names = {n["name"] for n in data["nodes"]}
    assert {"ИВАН ПЕТРОВ", "СТРОЙ ЕДНО ООД", "СТРОЙ ДВЕ ООД"} <= names
