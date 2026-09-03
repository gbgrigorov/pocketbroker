"""The upsert engine: natural-key writes, a field-level diff, and idempotency.

No FastAPI here — apply_bundle takes a session and flushes. Transaction control
(commit vs rollback for a dry run) belongs to the router.
"""

import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Builder, Entity
from app.sync.schemas import Bundle
from app.sync.upsert import apply_bundle


@pytest.fixture
def session():
    engine = create_engine("sqlite://", future=True,
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, future=True)()
    yield s
    s.close()


def _company(**kw):
    return {"kind": "company", "eik": "175376051", "name": "Артекс Златен век ООД", **kw}


def test_creates_a_company_entity(session):
    report = apply_bundle(session, Bundle(entities=[_company()]))
    assert report.tables["entity"].created == 1
    assert session.scalar(select(Entity).where(Entity.eik == "175376051")).name \
        == "Артекс Златен век ООД"


def test_second_identical_push_reports_unchanged(session):
    apply_bundle(session, Bundle(entities=[_company()]))
    report = apply_bundle(session, Bundle(entities=[_company()]))
    assert report.tables["entity"].created == 0
    assert report.tables["entity"].unchanged == 1
    assert session.scalar(select(Entity).where(Entity.eik == "175376051")) is not None


def test_update_is_reported_field_by_field(session):
    apply_bundle(session, Bundle(entities=[_company()]))
    report = apply_bundle(session, Bundle(entities=[_company(founded_year=2008)]))
    assert report.tables["entity"].updated == 1
    change = next(c for c in report.changes if c["field"] == "founded_year")
    assert change["from"] is None and change["to"] == 2008
    assert change["table"] == "entity" and change["key"] == "175376051"


def test_omitted_fields_never_erase(session):
    apply_bundle(session, Bundle(entities=[_company(address="София, ул. Х")]))
    apply_bundle(session, Bundle(entities=[_company()]))  # no address this time
    assert session.scalar(select(Entity).where(Entity.eik == "175376051")).address \
        == "София, ул. Х"


def test_builder_is_upserted_and_linked_to_its_entity(session):
    report = apply_bundle(session, Bundle(
        entities=[_company()],
        builder={"eik": "175376051", "name": "Артекс Златен век ООД",
                 "insolvency_flag": True},
    ))
    b = session.scalar(select(Builder).where(Builder.eik == "175376051"))
    assert b.insolvency_flag is True and b.entity_id is not None
    assert report.tables["builder"].created == 1


def test_corporate_shareholder_person_key_warns(session):
    # Papagal lists a company's own name among "related persons" with a synthetic
    # <eik>-N key. entity_for_person resolves it to the company; we warn so the
    # mis-typing is visible rather than silent.
    report = apply_bundle(session, Bundle(entities=[
        _company(),
        {"kind": "person", "person_key": "175376051-2", "name": "Артекс Златен век ООД"},
    ]))
    assert any("175376051" in w for w in report.warnings)


def test_report_serialises_to_json_safe_dict(session):
    report = apply_bundle(session, Bundle(entities=[_company(capital_eur=5000)]))
    json.dumps(report.as_dict())  # must not raise on Decimal/date
    assert report.as_dict()["tables"]["entity"]["created"] == 1
