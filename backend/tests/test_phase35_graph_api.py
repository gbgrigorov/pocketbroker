"""Phase-3.5 graph API: ego-network (depth-bounded) + global graph.

Direct vs indirect is not stored — only direct edges; the API computes the
depth-N subgraph by traversal. Verifies depth bounding, the induced-edge set,
node metadata for D3, and the "same person behind two builders" case.
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

# Graph: person P owns builders B1 and B2 (shared owner). B1 is also owned by
# company C, which person P2 owns. So from B1: depth1={P,C}, depth2 adds {B2,P2}.
BUILDERS = [{"eik": "B1", "name": "СТРОЙ ЕДНО ООД"}, {"eik": "B2", "name": "СТРОЙ ДВЕ ООД"}]
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


def test_ego_network_depth1_is_direct_only(client):
    data = client.get("/api/builders/B1/network?depth=1").json()
    names = {n["name"] for n in data["nodes"]}
    assert names == {"СТРОЙ ЕДНО ООД", "ИВАН ПЕТРОВ", "ХОЛДИНГ АД"}
    center = next(n for n in data["nodes"] if n["eik"] == "B1")
    assert center["is_builder"] is True and center["depth"] == 0
    # edges reference node ids and carry relation + provenance
    assert all({"source", "target", "relation"} <= set(e) for e in data["edges"])
    assert all(e["relation"] == "ownership" for e in data["edges"])


def test_ego_network_depth2_pulls_indirect(client):
    data = client.get("/api/builders/B1/network?depth=2").json()
    names = {n["name"] for n in data["nodes"]}
    # B2 (via shared person ИВАН) and P2 ГЕОРГИ (via ХОЛДИНГ) now appear
    assert {"СТРОЙ ДВЕ ООД", "ГЕОРГИ ДИМОВ"} <= names
    ivan = next(n for n in data["nodes"] if n["name"] == "ИВАН ПЕТРОВ")
    assert ivan["depth"] == 1
    b2 = next(n for n in data["nodes"] if n["eik"] == "B2")
    assert b2["depth"] == 2


def test_shared_owner_connects_two_builders(client):
    """The headline case: one person linking two builders shows both edges."""
    data = client.get("/api/builders/B1/network?depth=2").json()
    ivan = next(n for n in data["nodes"] if n["name"] == "ИВАН ПЕТРОВ")
    builder_ids = {n["id"] for n in data["nodes"] if n["is_builder"]}
    ivan_targets = {e["target"] for e in data["edges"] if e["source"] == ivan["id"]}
    assert builder_ids <= ivan_targets  # ИВАН owns both B1 and B2


def test_unknown_builder_404(client):
    assert client.get("/api/builders/ZZZ/network").status_code == 404


def test_global_graph_returns_nodes_and_edges(client):
    data = client.get("/api/graph").json()
    assert len(data["nodes"]) == 5      # B1, B2, C, ИВАН, ГЕОРГИ
    assert len(data["edges"]) >= 3
    assert any(n["is_builder"] for n in data["nodes"])
