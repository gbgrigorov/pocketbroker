"""Court / deep-research order endpoint + the pricing module.

Covers the pure price math (single + network block pricing, EIK+Name 3×), the
login gate, and that an order lands in the shared ``research_request`` inbox with
the server-computed quote. The price is never trusted from the client.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import pricing
from app.auth import current_user, current_user_optional
from app.db import Base, get_session
from app.main import app
from app.models import ResearchRequest
from etl.entities import OwnershipReport, load_ownership
from etl.load_phase3 import Phase3Report, load_builders

# B1 (company/builder) — depth1 adds person P and company C; depth2 adds B2 (via
# shared person P) and person P2. Companies-with-EIK reachable: B1, C, B2 = 3.
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


class _User:
    id = 7
    email = "member@example.com"
    is_active = True


@pytest.fixture
def client():
    engine = create_engine("sqlite://", future=True,
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    s = Session()
    load_builders(s, BUILDERS, Phase3Report())
    load_ownership(s, OWNERSHIP, OwnershipReport())
    s.commit()
    app.dependency_overrides[get_session] = lambda: s
    app.dependency_overrides[current_user] = lambda: _User()
    tc = TestClient(app)
    tc.Session = Session
    yield tc
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(current_user, None)
    s.close()


# --- pricing module (pure) ---------------------------------------------------

def test_quote_single():
    assert pricing.quote_single("eik") == 1.0
    assert pricing.quote_single("eik_name") == 3.0  # 3×


@pytest.mark.parametrize("count,expected", [(0, 0.0), (1, 3.0), (5, 3.0), (10, 3.0),
                                            (11, 6.0), (12, 6.0), (20, 6.0), (25, 9.0)])
def test_quote_network_blocks(count, expected):
    assert pricing.quote_network(count, "eik") == expected
    assert pricing.quote_network(count, "eik_name") == round(expected * 3, 2)


# --- endpoint ----------------------------------------------------------------

def test_requires_login(client):
    app.dependency_overrides.pop(current_user, None)  # restore the real auth dep
    app.dependency_overrides[current_user_optional] = lambda: None
    try:
        r = client.post("/api/research-requests/court-order",
                        json={"key": "B1", "scope": "company", "search_type": "eik"})
        assert r.status_code == 401
    finally:
        app.dependency_overrides.pop(current_user_optional, None)


def test_single_company_eik(client):
    r = client.post("/api/research-requests/court-order",
                    json={"key": "B1", "scope": "company", "search_type": "eik"})
    assert r.status_code == 201
    body = r.json()
    assert body["price_eur"] == 1.0 and body["entity_count"] == 1
    row = client.Session().scalars(select(ResearchRequest)).one()
    assert row.order_type == "court_research" and row.company_eik == "B1"
    assert float(row.price_eur) == 1.0 and row.scope == "company"


def test_single_company_eik_name_is_3x(client):
    r = client.post("/api/research-requests/court-order",
                    json={"key": "B1", "scope": "company", "search_type": "eik_name"})
    assert r.json()["price_eur"] == 3.0


def test_network_counts_companies_with_eik(client):
    r = client.post("/api/research-requests/court-order",
                    json={"key": "B1", "scope": "network", "search_type": "eik", "depth": 2})
    assert r.status_code == 201
    body = r.json()
    # B1, C, B2 are companies with EIK; persons P/P2 are excluded.
    assert body["entity_count"] == 3
    assert body["price_eur"] == pricing.quote_network(3, "eik")  # ceil(3/10)*3 = 3.0


def test_network_eik_name_is_3x(client):
    r = client.post("/api/research-requests/court-order",
                    json={"key": "B1", "scope": "network", "search_type": "eik_name", "depth": 2})
    assert r.json()["price_eur"] == pricing.quote_network(3, "eik_name")  # 9.0


def test_unknown_entity_404(client):
    r = client.post("/api/research-requests/court-order",
                    json={"key": "NOPE", "scope": "company", "search_type": "eik"})
    assert r.status_code == 404
