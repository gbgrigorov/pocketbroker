"""The natural-key entity helpers live in app/ so the API can use them without
importing the ETL package. This test pins the new import path and the
enrich-don't-erase contract the sync layer depends on."""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.entities import entity_for_company, entity_for_person, upsert_edge
from app.models import Entity
from app.names import norm_name


@pytest.fixture
def session():
    engine = create_engine("sqlite://", future=True,
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, future=True)()
    yield s
    s.close()


def test_norm_name_strips_legal_form_and_quotes():
    assert norm_name('„АРТЕКС ИНЖЕНЕРИНГ" АД') == "артекс инженеринг"
    assert norm_name(None) == ""


def test_company_upserts_on_eik_and_enriches(session):
    a, created = entity_for_company(session, "175376051", name="Артекс Златен век ООД")
    assert created is True
    b, created = entity_for_company(session, "175376051", founded_year=2008)
    assert created is False and b.id == a.id
    # the second call added a field without erasing the name from the first
    assert b.founded_year == 2008 and b.name == "Артекс Златен век ООД"


def test_capital_is_converted_from_eur(session):
    e, _ = entity_for_company(session, "111222333", name="X", capital_eur=1000)
    assert float(e.capital_bgn) == 1955.83


def test_person_upserts_on_person_key(session):
    p1, made = entity_for_person(session, "Иван Иванов", "abc-1")
    p2, made2 = entity_for_person(session, "Иван Иванов", "abc-1")
    assert made is True and made2 is False and p1.id == p2.id


def test_edge_upserts_on_natural_key(session):
    a, _ = entity_for_company(session, "111", name="A")
    b, _ = entity_for_company(session, "222", name="B")
    e1 = upsert_edge(session, a.id, b.id, "ownership", share_pct=50)
    e2 = upsert_edge(session, a.id, b.id, "ownership", share_pct=75)
    assert e1.id == e2.id and float(e2.share_pct) == 75
