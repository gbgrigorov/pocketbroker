"""Official-tier signals on a sibling company surface on the parent via a shared owner.

Conservative propagation: ONLY official-tier signals from a company co-owned/managed
by the same person bubble up (no forum/web), and only when explicitly requested
(detail view), never in the list. Mirrors the Артекс Златен век ООД → Артекс
Инженеринг АД case (bridge person: Елена Иванова).
"""
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Entity, EntityEdge, EntitySignal
from app.routes import _signal_counts_for, _signals_for


@pytest.fixture
def session():
    engine = create_engine("sqlite://", future=True,
                          connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, future=True)()
    yield s
    s.close()


def _build(session):
    parent = Entity(kind="company", eik="175155346", name="АРТЕКС ИНЖЕНЕРИНГ", is_builder=True)
    sibling = Entity(kind="company", eik="175376051", name="АРТЕКС ЗЛАТЕН ВЕК")
    person = Entity(kind="person", person_key="vesela", name="Елена Иванова")
    session.add_all([parent, sibling, person])
    session.flush()
    # person owns both companies
    session.add(EntityEdge(src_entity_id=person.id, dst_entity_id=parent.id,
                           relation="ownership", is_current=True))
    session.add(EntityEdge(src_entity_id=person.id, dst_entity_id=sibling.id,
                           relation="ownership", is_current=True))
    # an official-tier signal on the sibling, plus a forum signal on the sibling
    session.add(EntitySignal(entity_id=sibling.id, subject_kind="company",
                             matched_name="АРТЕКС ЗЛАТЕН ВЕК", source_type="registry",
                             tier="official", match_confidence="eik",
                             title="ВАС: разрешението е валидно", url="http://x/1"))
    session.add(EntitySignal(entity_id=sibling.id, subject_kind="company",
                             matched_name="АРТЕКС ЗЛАТЕН ВЕК", source_type="forum",
                             tier="community", match_confidence="fuzzy_low",
                             title="форумен коментар", url="http://x/2"))
    session.commit()
    return parent, sibling, person


def test_sibling_official_not_counted_without_flag(session):
    parent, _, _ = _build(session)
    counts = _signal_counts_for(session, parent.id)  # default: no siblings
    assert counts == {"official": 0, "community": 0, "web": 0}


def test_sibling_official_counted_with_flag(session):
    parent, _, _ = _build(session)
    counts = _signal_counts_for(session, parent.id, include_siblings=True)
    # the sibling's OFFICIAL signal bubbles up; its community one does NOT
    assert counts["official"] == 1
    assert counts["community"] == 0


def test_sibling_signal_has_via_label(session):
    parent, _, _ = _build(session)
    sigs = _signals_for(session, parent.id, include_siblings=True)
    official = [s for s in sigs if s["tier"] == "official"]
    assert len(official) == 1
    via = official[0]["subject"]
    assert "Елена Иванова" in via and "АРТЕКС ЗЛАТЕН ВЕК" in via


def test_hidden_signal_excluded_everywhere(session):
    """A signal flagged ``hidden=True`` is excluded both on its own entity's
    page and from a sibling's rollup."""
    parent, sibling, _ = _build(session)
    official = session.scalar(
        select(EntitySignal).where(EntitySignal.entity_id == sibling.id,
                                   EntitySignal.tier == "official")
    )
    official.hidden = True
    session.commit()

    # no longer shown on the sibling's own page
    own = _signals_for(session, sibling.id)
    assert not any(s["tier"] == "official" for s in own)

    # no longer rolled up onto the parent
    rolled = _signals_for(session, parent.id, include_siblings=True)
    assert not any(s["tier"] == "official" for s in rolled)

    counts = _signal_counts_for(session, parent.id, include_siblings=True)
    assert counts["official"] == 0
