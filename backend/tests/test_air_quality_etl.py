"""Unit tests for the air-quality ETL's neighbourhood→station mapping logic.

Uses an in-memory SQLite DB (same pattern as test_api.py) so the haversine /
nearest-station / 5km-cutoff / official-first logic is verified without the live
Postgres DB or the AQICN token.
"""
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import (AirQualityStation, City, Neighbourhood,
                        NeighbourhoodAirStation)

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "crawlers"))
from etl_air_quality import haversine_m, map_neighbourhoods  # noqa: E402


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://", future=True,
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    s = Session()
    yield s
    s.close()


def _sofia(session):
    city = City(name="София", slug="sofia")
    session.add(city)
    session.flush()
    n = Neighbourhood(city_id=city.id, name="Лозенец", slug="lozenets",
                      lat=42.66, lon=23.32)
    session.add(n)
    session.flush()
    return city, n


def test_haversine_known_distance():
    # 0.009° of latitude ≈ 1.0 km
    d = haversine_m(42.6600, 23.3200, 42.6690, 23.3200)
    assert 950 < d < 1050


def test_maps_neighbourhood_to_nearest_station(session):
    city, n = _sofia(session)
    near = AirQualityStation(name="Near", source="official", lat=42.665, lon=23.325,
                             city_id=city.id, external_id="A")
    far = AirQualityStation(name="Far", source="official", lat=42.60, lon=23.45,
                            city_id=city.id, external_id="B")
    session.add_all([near, far])
    session.flush()
    map_neighbourhoods(session)
    rows = session.scalars(select(NeighbourhoodAirStation)).all()
    assert len(rows) == 1
    assert rows[0].station_id == near.id


def test_skips_station_beyond_5km(session):
    city, n = _sofia(session)
    faraway = AirQualityStation(name="Faraway", source="official", lat=42.75, lon=23.32,
                                city_id=city.id, external_id="C")  # ~10 km north
    session.add(faraway)
    session.flush()
    map_neighbourhoods(session)
    rows = session.scalars(select(NeighbourhoodAirStation)).all()
    assert rows == []


def test_prefers_official_over_citizen_at_equal_distance(session):
    city, n = _sofia(session)
    # Identical coords → identical distance → official must win the tie-break.
    citizen = AirQualityStation(name="Cit", source="citizen", lat=42.665, lon=23.325,
                                city_id=city.id, external_id="D")
    official = AirQualityStation(name="Off", source="official", lat=42.665, lon=23.325,
                                 city_id=city.id, external_id="E")
    session.add_all([citizen, official])
    session.flush()
    map_neighbourhoods(session)
    row = session.scalars(select(NeighbourhoodAirStation)).one()
    assert row.station_id == official.id


def test_reruns_are_idempotent(session):
    city, n = _sofia(session)
    st = AirQualityStation(name="S", source="official", lat=42.665, lon=23.325,
                           city_id=city.id, external_id="F")
    session.add(st)
    session.flush()
    map_neighbourhoods(session)
    map_neighbourhoods(session)  # second run must not duplicate (deletes first)
    rows = session.scalars(select(NeighbourhoodAirStation)).all()
    assert len(rows) == 1
