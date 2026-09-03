"""Phase-3.5 tests: the entity/edge graph data model.

A *builder* is an :class:`Entity` of kind ``company`` flagged ``is_builder``;
``builder`` stays as the rich profile extension linked via ``builder.entity_id``.
Ownership/management connections live in :class:`EntityEdge` (directed,
idempotent on ``(src, dst, relation, valid_from)``). Direct vs indirect is not
stored — only direct edges; indirect = graph traversal.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_session
from app.main import app
from app.models import Builder, City, Entity, EntityEdge
from etl.entities import backfill_builder_entities, upsert_edge
from etl.load_phase3 import Phase3Report, load_builders

BUILDERS = [
    {"eik": "831641791", "name": "ПЛАНЕКС ЕООД", "legal_form": "ЕООД", "status": "active",
     "ksb_category": "I", "ksb_active": True},
    {"eik": "175074752", "name": "АРТЕКС ИНЖЕНЕРИНГ АД", "status": "active"},
]


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


def test_entity_and_edge_persist(session):
    """A company and a person node, joined by an ownership edge carrying a share."""
    company = Entity(kind="company", eik="831641791", name="ПЛАНЕКС ЕООД")
    person = Entity(kind="person", name="Иван Петров", person_key="ivan-petrov")
    session.add_all([company, person])
    session.flush()
    session.add(EntityEdge(
        src_entity_id=person.id, dst_entity_id=company.id,
        relation="ownership", share_pct=51.0, is_current=True,
    ))
    session.commit()

    edge = session.scalar(select(EntityEdge))
    assert edge.relation == "ownership"
    assert float(edge.share_pct) == 51.0
    assert edge.src_entity_id == person.id and edge.dst_entity_id == company.id


def test_load_builders_creates_linked_entities(session):
    """Loading builders backs each one with a company entity (is_builder)."""
    report = Phase3Report()
    load_builders(session, BUILDERS, report)
    session.commit()

    builders = session.scalars(select(Builder)).all()
    assert len(builders) == 2
    for b in builders:
        assert b.entity_id is not None
        assert b.entity.kind == "company"
        assert b.entity.is_builder is True
        assert b.entity.eik == b.eik
        assert b.entity.name == b.name


def test_backfill_is_idempotent(session):
    """Backfilling existing builders twice creates no duplicate entities."""
    report = Phase3Report()
    load_builders(session, BUILDERS, report)
    session.commit()

    # Simulate pre-3.5 rows that have no entity yet.
    for b in session.scalars(select(Builder)):
        b.entity_id = None
    session.execute(EntityEdge.__table__.delete())
    session.execute(Entity.__table__.delete())
    session.commit()

    created_first = backfill_builder_entities(session)
    session.commit()
    created_second = backfill_builder_entities(session)
    session.commit()

    assert created_first == 2
    assert created_second == 0
    assert session.scalar(select(func.count(Entity.id))) == 2


def test_upsert_edge_idempotent(session):
    """Same (src, dst, relation, valid_from) upserts once and updates in place."""
    a = Entity(kind="person", name="Иван Петров", person_key="ivan-petrov")
    b = Entity(kind="company", eik="831641791", name="ПЛАНЕКС ЕООД")
    session.add_all([a, b])
    session.flush()

    upsert_edge(session, a.id, b.id, "ownership", share_pct=50.0)
    session.commit()
    upsert_edge(session, a.id, b.id, "ownership", share_pct=51.0)  # share corrected
    session.commit()

    edges = session.scalars(select(EntityEdge)).all()
    assert len(edges) == 1
    assert float(edges[0].share_pct) == 51.0


def test_builder_detail_owners_and_managers_from_edges(session):
    """/api/builders/{eik} derives owners/managers from entity edges, not JSON."""
    report = Phase3Report()
    load_builders(session, BUILDERS, report)
    session.commit()

    planex = session.scalar(select(Builder).where(Builder.eik == "831641791"))
    owner = Entity(kind="company", eik="200000000", name="ПЛАНЕКС ХОЛДИНГ АД")
    mgr = Entity(kind="person", name="Георги Иванов", person_key="georgi-ivanov")
    session.add_all([owner, mgr])
    session.flush()
    upsert_edge(session, owner.id, planex.entity_id, "ownership", share_pct=100.0)
    upsert_edge(session, mgr.id, planex.entity_id, "management", role="управител")
    session.commit()

    app.dependency_overrides[get_session] = lambda: session
    client = TestClient(app)
    try:
        detail = client.get("/api/builders/831641791").json()
        assert [o["name"] for o in detail["owners"]] == ["ПЛАНЕКС ХОЛДИНГ АД"]
        assert detail["owners"][0]["share_pct"] == 100.0
        assert [m["name"] for m in detail["managers"]] == ["Георги Иванов"]
        assert detail["managers"][0]["role"] == "управител"
    finally:
        app.dependency_overrides.clear()
