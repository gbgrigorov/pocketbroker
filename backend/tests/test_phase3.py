"""Phase-3 tests: builder + new-building loaders, idempotency, and the API."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_session
from app.main import app
from app.models import Builder, City, Neighbourhood, NewBuilding, NewBuildingSource
from etl.load_phase3 import (Phase3Report, load_builders, load_crawl_runs,
                             load_new_buildings)


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://", future=True,
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, future=True)()
    city = City(name="София", slug="sofia")
    s.add(city)
    s.flush()
    s.add(Neighbourhood(city_id=city.id, name="Лозенец", slug="lozenets"))
    s.commit()
    yield s
    s.close()


BUILDERS = [
    {"eik": "831641791", "name": "ПЛАНЕКС ЕООД", "legal_form": "ЕООД", "status": "active",
     "ksb_category": "I", "ksb_active": True, "insolvency_flag": False, "tax_debt_bgn": None,
     "last_checked_at": "2026-05-31T10:00:00+00:00"},
    {"eik": "175074752", "name": "АРТЕКС ИНЖЕНЕРИНГ АД", "status": "active",
     "insolvency_flag": True, "tax_debt_bgn": 12000.0},
]

PROJECTS = [
    {"canonical_key": "sofia-lozenets-skyfort-residence", "name": "SkyFort Residence Lozenets",
     "developer_name": "ПЛАНЕКС", "neighborhood_slug": "lozenets", "akt_stage": "Акт 14",
     "completion_year": 2026, "floors": 12, "price_eur_sqm": 3350.0,
     "first_seen": "2026-05-31", "last_seen": "2026-05-31",
     "sources": [
         {"site": "novitesgradi", "source_name": "Sky Fort Residence", "url": "a", "price_eur_sqm": None,
          "scraped_at": "2026-05-31T10:00:00+00:00"},
         {"site": "bulgarianproperties", "source_name": "SkyFort Residence Lozenets", "url": "b",
          "price_eur_sqm": 3350.0, "scraped_at": "2026-05-31T11:00:00+00:00"},
     ]},
]


def test_load_builders_and_link_project(session):
    report = Phase3Report()
    load_builders(session, BUILDERS, report)
    load_new_buildings(session, PROJECTS, "sofia", report)
    session.commit()

    assert report.builders_upserted == 2
    assert report.new_buildings_upserted == 1
    assert report.new_building_sources == 2
    # "ПЛАНЕКС" developer name resolves to "ПЛАНЕКС ЕООД" builder via loose name match
    assert report.projects_linked_to_builder == 1
    nb = session.scalar(select(NewBuilding))
    assert nb.developer is not None and nb.developer.eik == "831641791"
    assert nb.neighbourhood_id is not None  # resolved to lozenets


def test_idempotent_reload(session):
    report = Phase3Report()
    load_builders(session, BUILDERS, report)
    load_new_buildings(session, PROJECTS, "sofia", report)
    session.commit()

    # Re-run with the same data — counts must not grow.
    load_builders(session, BUILDERS, Phase3Report())
    load_new_buildings(session, PROJECTS, "sofia", Phase3Report())
    session.commit()

    assert session.scalar(select(func.count(Builder.id))) == 2
    assert session.scalar(select(func.count(NewBuilding.id))) == 1
    # source rows are replaced, not duplicated
    assert session.scalar(select(func.count(NewBuildingSource.id))) == 2


def test_crawl_runs_dedupe(session):
    manifest = {"domain": "builders", "site": "ksb", "scope": "bg",
                "pages_fetched": 5, "bytes_downloaded": 1_500_000,
                "records_parsed": 100, "records_emitted": 100, "errors": 0,
                "duration_s": 3.2, "started_at": "2026-05-31T10:00:00+00:00"}
    report = Phase3Report()
    load_crawl_runs(session, [manifest, manifest], {}, report)  # same run twice
    session.commit()
    assert report.crawl_runs_loaded == 1
    assert report.crawl_runs_skipped == 1


def test_stats_and_builder_endpoints(session):
    report = Phase3Report()
    load_builders(session, BUILDERS, report)
    load_new_buildings(session, PROJECTS, "sofia", report)
    load_crawl_runs(session, [
        {"domain": "builders", "site": "ksb", "scope": "bg", "pages_fetched": 5,
         "bytes_downloaded": 2_000_000, "records_parsed": 100, "records_emitted": 100,
         "errors": 0, "duration_s": 3.0, "started_at": "2026-05-31T10:00:00+00:00"},
        {"domain": "new_buildings", "site": "novitesgradi", "scope": "sofia",
         "pages_fetched": 3, "bytes_downloaded": 1_000_000, "records_parsed": 40,
         "records_emitted": 40, "errors": 0, "duration_s": 2.0,
         "started_at": "2026-05-31T11:00:00+00:00"},
    ], {"sofia": 1}, report)
    session.commit()

    app.dependency_overrides[get_session] = lambda: session
    client = TestClient(app)
    try:
        stats = client.get("/api/stats").json()
        assert stats["data_scanned_mb"] == pytest.approx(3.0)
        assert stats["data_points"] == 140
        assert stats["builders"] == 2
        assert stats["projects"] == 1
        assert stats["sites"] == 2 and stats["scopes"] == 2

        # builders list + filters
        all_b = client.get("/api/builders").json()
        assert all_b["total"] == 2
        insolvent = client.get("/api/builders?insolvent=true").json()
        assert insolvent["total"] == 1 and insolvent["items"][0]["eik"] == "175074752"
        debtors = client.get("/api/builders?has_tax_debt=true").json()
        assert debtors["total"] == 1

        # builder detail carries linked projects
        detail = client.get("/api/builders/831641791").json()
        assert detail["name"] == "ПЛАНЕКС ЕООД"
        assert len(detail["projects"]) == 1

        # project endpoint exposes the cross-site source trail
        projects = client.get("/api/cities/sofia/projects").json()
        assert len(projects) == 1
        assert {s["site"] for s in projects[0]["sources"]} == {"novitesgradi", "bulgarianproperties"}
    finally:
        app.dependency_overrides.clear()
