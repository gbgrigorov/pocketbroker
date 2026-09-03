"""Builder.insolvency_flag is derived from the backing entity's Papagal status."""
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Builder, Entity
from etl.entities import derive_insolvency_flags


@pytest.fixture
def session():
    engine = create_engine("sqlite://", future=True,
                          connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, future=True)()
    yield s
    s.close()


def test_derives_flag_from_status(session):
    e = Entity(kind="company", eik="111", name="X", is_builder=True, status="В несъстоятелност")
    session.add(e); session.flush()
    session.add(Builder(eik="111", name="X", entity_id=e.id)); session.commit()
    assert derive_insolvency_flags(session) == 1
    session.commit()
    assert session.scalar(select(Builder).where(Builder.eik == "111")).insolvency_flag is True


def test_active_builder_not_flagged(session):
    e = Entity(kind="company", eik="222", name="Y", is_builder=True, status="Активен")
    session.add(e); session.flush()
    session.add(Builder(eik="222", name="Y", entity_id=e.id)); session.commit()
    derive_insolvency_flags(session); session.commit()
    assert session.scalar(select(Builder).where(Builder.eik == "222")).insolvency_flag is False
