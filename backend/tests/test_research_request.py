"""Public "order a research" lead-capture endpoint + its guards.

Covers the happy path plus everything that must *fail closed*: the math CAPTCHA
(wrong/forged/expired), the honeypot, schema validation, and the whitelist
sanitiser (injection/markup payloads come out clean; real Cyrillic names survive).
"""

import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import captcha
from app.auth import current_user_optional
from app.db import Base, get_session
from app.main import app
from app.models import ResearchRequest


@pytest.fixture
def client():
    engine = create_engine("sqlite://", future=True,
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = override
    tc = TestClient(app)
    tc.Session = Session  # expose for read-back assertions
    yield tc
    app.dependency_overrides.pop(get_session, None)


def solved(c):
    """Fetch a real challenge and return a valid (answer, exp, sig) triple."""
    ch = c.get("/api/research-requests/challenge").json()
    a, b = (int(x) for x in ch["question"].split(" + "))
    return {"captcha_answer": a + b, "captcha_exp": ch["exp"], "captcha_sig": ch["sig"]}


def body(c, **over):
    payload = {"company_name": "Artex OOD", "requester_email": "lead@example.com"}
    payload.update(solved(c))
    payload.update(over)
    return payload


# --- happy path --------------------------------------------------------------

def test_submit_stores_row(client):
    r = client.post("/api/research-requests", json=body(
        client, company_name="Lozenets Build", company_eik="123456789",
        owner="Ivan Petrov", details="Please check this developer.",
        requester_name="Maria", search_query="lozenets build",
    ))
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["status"] == "new" and isinstance(out["id"], int)
    # PII is not echoed back.
    assert "requester_email" not in out

    with client.Session() as s:
        row = s.scalars(select(ResearchRequest)).one()
    assert row.company_name == "Lozenets Build"
    assert row.company_eik == "123456789"
    assert row.requester_email == "lead@example.com"
    assert row.user_id == 1  # conftest default_authenticated Member


def test_anonymous_submit_has_null_user(client):
    app.dependency_overrides[current_user_optional] = lambda: None
    try:
        r = client.post("/api/research-requests", json=body(client))
        assert r.status_code == 201, r.text
    finally:
        app.dependency_overrides.pop(current_user_optional, None)
    with client.Session() as s:
        assert s.scalars(select(ResearchRequest)).one().user_id is None


# --- CAPTCHA: must fail closed ----------------------------------------------

def test_wrong_answer_rejected(client):
    p = body(client)
    p["captcha_answer"] += 1
    r = client.post("/api/research-requests", json=p)
    assert r.status_code == 400 and r.json()["detail"] == "captcha"
    assert _count(client) == 0


def test_forged_signature_rejected(client):
    p = body(client)
    p["captcha_sig"] = "deadbeef" * 8
    r = client.post("/api/research-requests", json=p)
    assert r.status_code == 400
    assert _count(client) == 0


def test_expired_challenge_rejected(client):
    past = int(time.time()) - 1
    # A *correctly signed* but expired triple still fails on the expiry check.
    p = body(client, captcha_answer=5, captcha_exp=past, captcha_sig=captcha._sign(5, past))
    r = client.post("/api/research-requests", json=p)
    assert r.status_code == 400
    assert _count(client) == 0


# --- schema + honeypot guards ------------------------------------------------

def test_honeypot_filled_rejected(client):
    r = client.post("/api/research-requests", json=body(client, website="http://spam"))
    assert r.status_code == 422
    assert _count(client) == 0


def test_missing_required_fields_rejected(client):
    no_company = body(client)
    no_company.pop("company_name")
    assert client.post("/api/research-requests", json=no_company).status_code == 422

    no_email = body(client)
    no_email.pop("requester_email")
    assert client.post("/api/research-requests", json=no_email).status_code == 422


def test_bad_eik_rejected(client):
    assert client.post("/api/research-requests",
                       json=body(client, company_eik="12")).status_code == 422
    assert client.post("/api/research-requests",
                       json=body(client, company_eik="abcdefghi")).status_code == 422


def test_overlong_details_rejected(client):
    r = client.post("/api/research-requests", json=body(client, details="x" * 2001))
    assert r.status_code == 422


def test_unknown_field_rejected(client):
    r = client.post("/api/research-requests", json=body(client, evil="1"))
    assert r.status_code == 422


# --- whitelist sanitiser -----------------------------------------------------

def test_sql_payload_is_sanitised_not_executed(client):
    r = client.post("/api/research-requests", json=body(
        client, company_name="Robert'); DROP TABLE research_request;--"))
    assert r.status_code == 201, r.text
    with client.Session() as s:
        row = s.scalars(select(ResearchRequest)).one()  # table still exists
    # The dangerous punctuation is gone; only whitelisted chars remain.
    for ch in [";", "\\", "<", ">"]:
        assert ch not in row.company_name
    # Whatever survives is inert literal text (the .one() above proves the table
    # was never dropped). The underscore is also non-whitelisted, so it's stripped.
    assert "DROP TABLE" in row.company_name


def test_cyrillic_name_round_trips(client):
    r = client.post("/api/research-requests", json=body(client, company_name="Артекс ООД & Со."))
    assert r.status_code == 201, r.text
    with client.Session() as s:
        assert s.scalars(select(ResearchRequest)).one().company_name == "Артекс ООД & Со."


def test_html_in_details_is_stripped(client):
    r = client.post("/api/research-requests",
                    json=body(client, details="<script>alert(1)</script>"))
    assert r.status_code == 201, r.text
    with client.Session() as s:
        details = s.scalars(select(ResearchRequest)).one().details
    assert "<" not in details and ">" not in details
    assert details == "scriptalert(1)/script"


def _count(client):
    with client.Session() as s:
        return len(s.scalars(select(ResearchRequest)).all())


# --- pay-to-expedite ---------------------------------------------------------

def test_default_is_plain_queued_lead(client):
    r = client.post("/api/research-requests", json=body(client))
    assert r.status_code == 201, r.text
    assert r.json()["price_eur"] is None
    with client.Session() as s:
        row = s.scalars(select(ResearchRequest)).one()
    assert row.order_type == "lead" and row.expedited is False and row.price_eur is None


def test_expedite_with_eik_prices_one_euro(client):
    r = client.post("/api/research-requests",
                    json=body(client, company_eik="831641791", expedited=True, search_type="eik"))
    assert r.status_code == 201, r.text
    assert r.json()["price_eur"] == 1.0
    with client.Session() as s:
        row = s.scalars(select(ResearchRequest)).one()
    assert row.order_type == "court_research" and row.expedited is True
    assert float(row.price_eur) == 1.0 and row.entity_count == 1


def test_expedite_without_eik_defaults_to_name_pricing(client):
    r = client.post("/api/research-requests", json=body(client, expedited=True))
    assert r.status_code == 201, r.text
    assert r.json()["price_eur"] == 3.0  # name-only is the fuzzier 3× tier
