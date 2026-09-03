"""Delivery fields on research_request + the sync audit log."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import ResearchRequest, SyncLog


@pytest.fixture
def session():
    engine = create_engine("sqlite://", future=True,
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, future=True)()
    yield s
    s.close()


def test_request_carries_delivery_fields(session):
    r = ResearchRequest(company_name="X", requester_email="a@b.c",
                        report_md="# findings", notes="internal",
                        delivered_at=datetime(2026, 8, 20, 10, 0))
    session.add(r)
    session.commit()
    assert r.report_md == "# findings" and r.notes == "internal"
    assert r.delivered_at.year == 2026


def test_sync_log_stores_a_json_summary(session):
    log = SyncLog(action="findings", dry_run=True,
                  summary={"tables": {"entity": {"created": 2}}})
    session.add(log)
    session.commit()
    assert log.summary["tables"]["entity"]["created"] == 2
    assert log.dry_run is True and log.request_id is None
