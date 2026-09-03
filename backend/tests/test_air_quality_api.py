"""GET /api/map air-quality extension: each neighbourhood carries an `air` key
holding seasonal averages — {year: {winter: {pm25, aqi, n}, summer: {...}}} — or
null when the neighbourhood has no air rows."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_session
from app.main import app
from app.models import City, Neighbourhood, NeighbourhoodAir
from app.routes import clear_caches


@pytest.fixture
def client():
    clear_caches()
    engine = create_engine(
        "sqlite://", future=True,
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    session = Session()

    sofia = City(name="София", slug="sofia")
    session.add(sofia)
    session.flush()
    loz = Neighbourhood(city_id=sofia.id, name="Лозенец", slug="lozenets",
                        lat=42.66, lon=23.32)
    nad = Neighbourhood(city_id=sofia.id, name="Надежда", slug="nadezhda",
                        lat=42.73, lon=23.30)
    session.add_all([loz, nad])
    session.flush()

    # lozenets has two seasons in 2024 + a 2023 winter; nadezhda has no air rows.
    session.add_all([
        NeighbourhoodAir(neighbourhood_id=loz.id, year=2024, season="winter",
                         pm25_avg=24.1, aqi_avg=76.0, sensor_count=9),
        NeighbourhoodAir(neighbourhood_id=loz.id, year=2024, season="summer",
                         pm25_avg=9.2, aqi_avg=38.0, sensor_count=9),
        NeighbourhoodAir(neighbourhood_id=loz.id, year=2023, season="winter",
                         pm25_avg=28.0, aqi_avg=85.0, sensor_count=7),
    ])
    session.commit()

    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()
    session.close()


def test_neighbourhood_has_seasonal_air(client):
    data = client.get("/api/map?city=sofia").json()
    loz = next(f for f in data if f["slug"] == "lozenets")
    assert set(loz["air"].keys()) == {"2023", "2024"}
    assert loz["air"]["2024"]["winter"]["pm25"] == pytest.approx(24.1)
    assert loz["air"]["2024"]["winter"]["aqi"] == pytest.approx(76.0)
    assert loz["air"]["2024"]["winter"]["n"] == 9
    assert loz["air"]["2024"]["summer"]["pm25"] == pytest.approx(9.2)


def test_winter_worse_than_summer(client):
    """Sanity: the seasonal split actually carries the winter spike."""
    data = client.get("/api/map?city=sofia").json()
    loz = next(f for f in data if f["slug"] == "lozenets")
    assert loz["air"]["2024"]["winter"]["pm25"] > loz["air"]["2024"]["summer"]["pm25"]


def test_neighbourhood_without_air_is_null(client):
    data = client.get("/api/map?city=sofia").json()
    nad = next(f for f in data if f["slug"] == "nadezhda")
    assert nad["air"] is None


def test_air_does_not_break_existing_price_fields(client):
    data = client.get("/api/map?city=sofia").json()
    loz = next(f for f in data if f["slug"] == "lozenets")
    assert "by_year" in loz and "latest" in loz
    assert loz["lat"] == pytest.approx(42.66)
