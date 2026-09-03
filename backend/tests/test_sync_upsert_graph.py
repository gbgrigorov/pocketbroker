"""Edges, signals and court checks — the parts of a bundle that reference
entities by natural key and must stay idempotent across re-pushes."""

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import CourtCheck, EntityEdge, EntitySignal
from app.sync.schemas import Bundle
from app.sync.upsert import BundleError, apply_bundle


@pytest.fixture
def session():
    engine = create_engine("sqlite://", future=True,
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, future=True)()
    yield s
    s.close()


ENTITIES = [
    {"kind": "company", "eik": "175376051", "name": "Артекс Златен век ООД"},
    {"kind": "person", "person_key": "p-1", "name": "Иван Иванов"},
]


def test_edge_resolves_entities_created_in_the_same_bundle(session):
    report = apply_bundle(session, Bundle(entities=ENTITIES, edges=[
        {"src": {"person_key": "p-1"}, "dst": {"eik": "175376051"},
         "relation": "ownership", "share_pct": 50},
    ]))
    edge = session.scalar(select(EntityEdge))
    assert edge is not None and float(edge.share_pct) == 50
    assert report.tables["entity_edge"].created == 1


def test_edge_to_an_unknown_entity_raises(session):
    with pytest.raises(BundleError, match="999999999"):
        apply_bundle(session, Bundle(entities=ENTITIES, edges=[
            {"src": {"eik": "999999999"}, "dst": {"eik": "175376051"},
             "relation": "ownership"},
        ]))


def test_signal_upserts_on_url_and_matched_name(session):
    sig = {"subject_kind": "company", "matched_name": "Артекс Златен век ООД",
           "matched_eik": "175376051", "source_type": "registry", "tier": "official",
           "match_confidence": "eik",
           "url": "https://legalacts.justice.bg/Search/GetAct?actId=123"}
    apply_bundle(session, Bundle(entities=ENTITIES, signals=[sig]))
    apply_bundle(session, Bundle(entities=ENTITIES, signals=[sig]))
    assert session.scalar(select(func.count()).select_from(EntitySignal)) == 1
    assert session.scalar(select(EntitySignal)).entity_id is not None


def test_same_act_url_can_belong_to_two_companies(session):
    # One court actId legitimately names several companies. The key is
    # (url, matched_name), so both rows survive.
    url = "https://legalacts.justice.bg/Search/GetAct?actId=123"
    apply_bundle(session, Bundle(
        entities=[{"kind": "company", "eik": "111", "name": "А ООД"},
                  {"kind": "company", "eik": "222", "name": "Б ООД"}],
        signals=[
            {"subject_kind": "company", "matched_name": "А ООД", "matched_eik": "111",
             "source_type": "registry", "tier": "official",
             "match_confidence": "eik", "url": url},
            {"subject_kind": "company", "matched_name": "Б ООД", "matched_eik": "222",
             "source_type": "registry", "tier": "official",
             "match_confidence": "eik", "url": url},
        ]))
    rows = session.scalars(select(EntitySignal)).all()
    assert len(rows) == 2
    assert {r.matched_eik for r in rows} == {"111", "222"}
    assert len({r.entity_id for r in rows}) == 2  # resolved per entity, not per url


def test_court_check_is_appended_once_per_distinct_check(session):
    check = {"eik": "175376051", "checked_at": "2026-08-20T10:00:00",
             "method": "eik", "acts_found": 3}
    apply_bundle(session, Bundle(entities=ENTITIES, court_checks=[check]))
    report = apply_bundle(session, Bundle(entities=ENTITIES, court_checks=[check]))
    assert session.scalar(select(func.count()).select_from(CourtCheck)) == 1
    assert report.tables["court_check"].skipped == 1

    later = dict(check, checked_at="2026-08-21T10:00:00")
    apply_bundle(session, Bundle(entities=ENTITIES, court_checks=[later]))
    assert session.scalar(select(func.count()).select_from(CourtCheck)) == 2
