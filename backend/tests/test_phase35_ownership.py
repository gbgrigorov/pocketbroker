"""Phase-3.5 ownership ETL: raw Papagal edge records -> entity graph.

Verifies provenance (every node/edge records its ``source``), person dedup by
``person_key`` across companies, correct edge direction, idempotency, and the
headline case — one person behind several companies.
"""

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Builder, City, Entity, EntityEdge
from etl.entities import OwnershipReport, load_ownership
from etl.load_phase3 import Phase3Report, load_builders

PERSON_KEY = "556ae17551059d1122334455"

REC_TEKO = {
    "eik": "041044484", "name": "ТЕКО АД", "legal_form": "Акционерно дружество (АД)",
    "status": "Активен", "address": "БЪЛГАРИЯ, гр. София", "capital_eur": 102240.0,
    "source": "papagal",
    "related": [
        {"kind": "person", "name": "АСЕН ИВАНОВ АСЕНОВ", "person_key": PERSON_KEY,
         "relation": "ownership", "role": "Действителен собственик",
         "direction": "in", "is_current": True},
        {"kind": "person", "name": "АСЕН ИВАНОВ АСЕНОВ", "person_key": PERSON_KEY,
         "relation": "management", "role": "Съвет на директорите",
         "direction": "in", "is_current": True},
    ],
}
REC_OTHER = {
    "eik": "999999999", "name": "ДРУГА ФИРМА ЕООД", "status": "Активен", "source": "papagal",
    "related": [
        {"kind": "person", "name": "АСЕН ИВАНОВ АСЕНОВ", "person_key": PERSON_KEY,
         "relation": "ownership", "role": "Едноличен собственик",
         "direction": "in", "is_current": True},
    ],
}


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://", future=True,
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, future=True)()
    s.add(City(name="София", slug="sofia"))
    s.commit()
    yield s
    s.close()


def test_ownership_load_builds_graph_with_provenance(session):
    # ТЕКО already exists as a builder (has its company entity).
    load_builders(session, [{"eik": "041044484", "name": "ТЕКО АД", "ksb_active": True}],
                  Phase3Report())
    session.commit()

    report = OwnershipReport()
    load_ownership(session, [REC_TEKO, REC_OTHER], report)
    session.commit()

    # ТЕКО's builder entity is reused, not duplicated, and stays a builder.
    teko = session.scalars(select(Entity).where(Entity.eik == "041044484")).all()
    assert len(teko) == 1
    assert teko[0].is_builder is True

    # The person is one node despite appearing on two companies.
    persons = session.scalars(select(Entity).where(Entity.person_key == PERSON_KEY)).all()
    assert len(persons) == 1
    person = persons[0]
    assert person.kind == "person"
    assert person.source == "papagal"

    # Edges: person owns ТЕКО, manages ТЕКО, owns ДРУГА ФИРМА — directed person -> company.
    edges = session.scalars(select(EntityEdge)).all()
    assert len(edges) == 3
    assert all(e.source == "papagal" for e in edges)
    assert all(e.src_entity_id == person.id for e in edges)

    # Headline case: the same person behind two companies (two ownership edges out).
    owned = session.scalars(
        select(EntityEdge).where(EntityEdge.src_entity_id == person.id,
                                 EntityEdge.relation == "ownership")
    ).all()
    assert len(owned) == 2


REC_PERSON = {
    "kind": "person_participations", "person_key": PERSON_KEY,
    "name": "АСЕН ИВАНОВ АСЕНОВ", "source": "papagal",
    "companies": [
        {"kind": "company", "eik": "041044484", "name": "ТЕКО АД",
         "relation": "ownership", "role": "Действителен собственик",
         "share_pct": None, "is_current": True},
        {"kind": "company", "eik": "111222333", "name": "НОВ ПРОЕКТ ЕООД",
         "relation": "ownership", "role": "Едноличен собственик на капитала",
         "share_pct": 100.0, "is_current": True},
        {"kind": "company", "eik": "444555666", "name": "СТАРА ФИРМА ООД",
         "relation": "management", "role": "Управител",
         "share_pct": None, "is_current": False},
    ],
}


def test_person_participations_expand_graph(session):
    """A depth-2 person record adds the OTHER companies behind that person."""
    report = OwnershipReport()
    load_ownership(session, [REC_PERSON], report)
    session.commit()

    person = session.scalar(select(Entity).where(Entity.person_key == PERSON_KEY))
    assert person is not None
    # three companies discovered behind this person
    companies = session.scalars(select(Entity).where(Entity.kind == "company")).all()
    assert {c.eik for c in companies} == {"041044484", "111222333", "444555666"}

    edges = session.scalars(select(EntityEdge)).all()
    assert len(edges) == 3
    assert all(e.src_entity_id == person.id for e in edges)  # person -> company
    assert all(e.source == "papagal" for e in edges)

    # share % and current flag are carried onto the edge
    nov = session.scalar(select(Entity).where(Entity.eik == "111222333"))
    nov_edge = session.scalar(select(EntityEdge).where(EntityEdge.dst_entity_id == nov.id))
    assert float(nov_edge.share_pct) == 100.0 and nov_edge.is_current is True
    stara = session.scalar(select(Entity).where(Entity.eik == "444555666"))
    stara_edge = session.scalar(select(EntityEdge).where(EntityEdge.dst_entity_id == stara.id))
    assert stara_edge.relation == "management" and stara_edge.is_current is False


def test_ownership_load_is_idempotent(session):
    load_ownership(session, [REC_TEKO, REC_OTHER], OwnershipReport())
    session.commit()
    load_ownership(session, [REC_TEKO, REC_OTHER], OwnershipReport())
    session.commit()

    assert session.scalar(select(func.count(Entity.id))) == 3      # 2 companies + 1 person
    assert session.scalar(select(func.count(EntityEdge.id))) == 3  # no duplicate edges
