"""Unit tests for the seasonal neighbourhood-air aggregation ETL.

In-memory SQLite (test_api.py pattern). Verifies sensors are averaged into the
right neighbourhood per (year, season), the 2 km assignment cutoff, and idempotent
re-runs — without the live archive or DB.
"""
import json
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import City, Neighbourhood, NeighbourhoodAir

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "crawlers"))
from etl_neighbourhood_air import aggregate, nearest_neighbourhood  # noqa: E402


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
    loz = Neighbourhood(city_id=city.id, name="Лозенец", slug="lozenets",
                        lat=42.660, lon=23.320)
    session.add(loz)
    session.flush()
    return city, loz


def _write_jsonl(tmp_path, year, rows):
    f = tmp_path / f"sc_sofia_{year}.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in rows))
    return f


def test_nearest_neighbourhood_within_cutoff(session):
    _, loz = _sofia(session)
    nbhds = session.scalars(select(Neighbourhood)).all()
    assert nearest_neighbourhood(42.661, 23.321, nbhds) == loz.id  # ~140 m
    assert nearest_neighbourhood(42.80, 23.50, nbhds) is None       # far away


def test_averages_sensors_per_season(session, tmp_path):
    _, loz = _sofia(session)
    # two sensors inside lozenets, winter 2024: 20 and 30 → avg 25
    _write_jsonl(tmp_path, 2024, [
        {"uid": 1, "lat": 42.660, "lon": 23.320, "year": 2024, "season": "winter", "pm25": 20.0, "aqi": 68.0},
        {"uid": 2, "lat": 42.661, "lon": 23.321, "year": 2024, "season": "winter", "pm25": 30.0, "aqi": 89.0},
        {"uid": 1, "lat": 42.660, "lon": 23.320, "year": 2024, "season": "summer", "pm25": 8.0, "aqi": 33.0},
    ])
    aggregate(session, tmp_path)
    rows = {(r.year, r.season): r for r in session.scalars(select(NeighbourhoodAir)).all()}
    assert rows[(2024, "winter")].pm25_avg == pytest.approx(25.0)
    assert rows[(2024, "winter")].sensor_count == 2
    assert rows[(2024, "summer")].pm25_avg == pytest.approx(8.0)
    assert rows[(2024, "summer")].sensor_count == 1


def test_sensor_outside_cutoff_is_dropped(session, tmp_path):
    _sofia(session)
    _write_jsonl(tmp_path, 2024, [
        {"uid": 9, "lat": 42.80, "lon": 23.50, "year": 2024, "season": "winter", "pm25": 50.0, "aqi": 137.0},
    ])
    aggregate(session, tmp_path)
    assert session.scalars(select(NeighbourhoodAir)).all() == []


def test_rerun_is_idempotent(session, tmp_path):
    _sofia(session)
    _write_jsonl(tmp_path, 2024, [
        {"uid": 1, "lat": 42.660, "lon": 23.320, "year": 2024, "season": "winter", "pm25": 20.0, "aqi": 68.0},
    ])
    aggregate(session, tmp_path)
    aggregate(session, tmp_path)
    assert len(session.scalars(select(NeighbourhoodAir)).all()) == 1
