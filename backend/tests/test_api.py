from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_session
from app.main import app
from app.models import City, GoldPrice, MinWage, Neighbourhood, PriceSnapshot
from app.routes import clear_caches


@pytest.fixture
def client():
    clear_caches()  # /map + /cities cache is module-level; isolate each test's DB
    engine = create_engine(
        "sqlite://", future=True,
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    session = Session()

    city = City(name="София", slug="sofia")
    varna = City(name="Варна", slug="varna")
    session.add_all([city, varna])
    session.flush()
    loz = Neighbourhood(city_id=city.id, name="Лозенец", slug="lozenets", lat=42.66, lon=23.32)
    izg = Neighbourhood(city_id=city.id, name="Изгрев", slug="izgrev", lat=42.67, lon=23.35)
    # Same slug as a Sofia neighbourhood would never collide here, but Varna gets
    # its own "tsentar" to prove per-city slug resolution.
    vc = Neighbourhood(city_id=varna.id, name="Център", slug="tsentar", lat=43.20, lon=27.91)
    session.add_all([loz, izg, vc])
    session.flush()
    session.add_all([
        PriceSnapshot(neighbourhood_id=loz.id, property_type="двустаен", transaction_type="sale",
                      price_eur=180000, price_eur_sqm=3000,
                      overall_avg_eur_sqm=3100, period_date=date(2024, 10, 1)),
        PriceSnapshot(neighbourhood_id=loz.id, property_type="тристаен", transaction_type="sale",
                      price_eur=300000, price_eur_sqm=3200,
                      overall_avg_eur_sqm=3100, period_date=date(2024, 10, 1)),
        PriceSnapshot(neighbourhood_id=loz.id, property_type="двустаен", transaction_type="sale",
                      price_eur=204000, price_eur_sqm=3400,
                      overall_avg_eur_sqm=3500, period_date=date(2025, 10, 1)),
        # a rent row for lozenets 2025
        PriceSnapshot(neighbourhood_id=loz.id, property_type="двустаен", transaction_type="rent",
                      price_eur=700, price_eur_sqm=12,
                      overall_avg_eur_sqm=11, period_date=date(2025, 10, 1)),
        PriceSnapshot(neighbourhood_id=izg.id, property_type="двустаен", transaction_type="sale",
                      price_eur=170000, price_eur_sqm=2800,
                      overall_avg_eur_sqm=2800, period_date=date(2025, 10, 1)),
        PriceSnapshot(neighbourhood_id=vc.id, property_type="двустаен", transaction_type="sale",
                      price_eur=160000, price_eur_sqm=2000,
                      overall_avg_eur_sqm=2000, period_date=date(2025, 10, 1)),
    ])
    session.add_all([
        GoldPrice(period_date=date(2025, 10, 1), price_eur_per_gram=80.0, source="t"),
        MinWage(year=2025, amount_eur=551.0, amount_bgn=1077.0, source="t"),
    ])
    session.commit()

    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()
    session.close()


def test_map_returns_all_neighbourhoods_with_coords(client):
    data = client.get("/api/map").json()
    assert {f["slug"] for f in data} == {"lozenets", "izgrev", "tsentar"}
    loz = next(f for f in data if f["slug"] == "lozenets")
    assert loz["name"] == "Лозенец"
    assert loz["lat"] == pytest.approx(42.66)
    assert loz["lon"] == pytest.approx(23.32)


def test_map_city_filter(client):
    """?city restricts the bubble field to a single city's neighbourhoods."""
    sofia = client.get("/api/map?city=sofia").json()
    assert {f["slug"] for f in sofia} == {"lozenets", "izgrev"}
    varna = client.get("/api/map?city=varna").json()
    assert {f["slug"] for f in varna} == {"tsentar"}


def test_cities_endpoint(client):
    data = client.get("/api/cities").json()
    by_slug = {c["slug"]: c for c in data}
    assert set(by_slug) == {"sofia", "varna"}
    # Sofia has two mapped neighbourhoods, Varna one → Sofia first (busiest).
    assert [c["slug"] for c in data] == ["sofia", "varna"]
    assert by_slug["sofia"]["neighbourhood_count"] == 2
    # Centroid = mean of neighbourhood coords.
    assert by_slug["sofia"]["lat"] == pytest.approx((42.66 + 42.67) / 2)
    assert by_slug["sofia"]["lon"] == pytest.approx((23.32 + 23.35) / 2)
    # avg_eur_sqm = mean of latest overall sale €/m² (lozenets 3500, izgrev 2800).
    assert by_slug["sofia"]["avg_eur_sqm"] == pytest.approx((3500 + 2800) / 2)
    assert by_slug["varna"]["avg_eur_sqm"] == pytest.approx(2000)


def test_neighbourhood_lookup_is_city_scoped(client):
    """Same slug in two cities resolves to the right one via ?city."""
    varna_c = client.get("/api/neighbourhoods/tsentar?city=varna").json()
    assert varna_c["name"] == "Център"
    assert varna_c["lat"] == pytest.approx(43.20)
    # Sofia has no "tsentar" → 404 when constrained to sofia.
    assert client.get("/api/neighbourhoods/tsentar?city=sofia").status_code == 404


def test_map_latest_is_latest_period_overall_avg(client):
    """`latest` carries the most-recent-period overall avg (2025, not 2024)."""
    data = client.get("/api/map").json()
    loz = next(f for f in data if f["slug"] == "lozenets")
    assert loz["latest"]["sale"] == pytest.approx(3500)  # 2025 overall, not 2024


def test_map_by_year_carries_every_year(client):
    """All years travel together so the slider filters client-side — no ?year refetch."""
    data = client.get("/api/map").json()
    loz = next(f for f in data if f["slug"] == "lozenets")
    assert loz["by_year"]["2024"]["sale"] == pytest.approx(3100)
    assert loz["by_year"]["2025"]["sale"] == pytest.approx(3500)
    izg = next(f for f in data if f["slug"] == "izgrev")
    assert "2024" not in izg["by_year"]  # no 2024 data for izgrev → absent (renders as null)


def test_map_latest_carries_sale_and_rent_for_ptr(client):
    """Bubble field computes PtR client-side, so each year exposes both €/m² values."""
    data = client.get("/api/map").json()
    loz = next(f for f in data if f["slug"] == "lozenets")
    assert loz["latest"]["sale"] == pytest.approx(3500)
    assert loz["latest"]["rent"] == pytest.approx(11)        # 2025 rent overall avg
    assert loz["by_year"]["2025"]["rent"] == pytest.approx(11)
    izg = next(f for f in data if f["slug"] == "izgrev")
    assert izg["latest"]["rent"] is None                      # no rent rows for izgrev


def test_map_is_cached_and_refreshable(client, monkeypatch):
    """/map serves from the in-memory cache; the guarded refresh endpoint clears it."""
    first = client.get("/api/map?city=sofia").json()
    # The cache key is populated now; refresh requires the ADMIN_TOKEN.
    assert client.post("/api/admin/refresh-cache").status_code == 403  # unset → fail closed
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret")
    assert client.post("/api/admin/refresh-cache",
                       headers={"x-admin-token": "wrong"}).status_code == 403
    ok = client.post("/api/admin/refresh-cache", headers={"x-admin-token": "s3cret"})
    assert ok.status_code == 200 and ok.json()["cleared"] is True
    # Still serves correctly after a clear (recomputed).
    assert {f["slug"] for f in client.get("/api/map?city=sofia").json()} == \
        {f["slug"] for f in first}


def test_prices_returns_overall_series_in_time_order(client):
    data = client.get("/api/neighbourhoods/lozenets/prices").json()
    assert data["name"] == "Лозенец"
    series = data["series"]
    assert [p["period_date"] for p in series] == ["2024-10-01", "2025-10-01"]
    assert [p["price_eur_sqm"] for p in series] == pytest.approx([3100, 3500])


def test_prices_unknown_slug_404(client):
    assert client.get("/api/neighbourhoods/nope/prices").status_code == 404


def test_neighbourhood_meta(client):
    data = client.get("/api/neighbourhoods/lozenets").json()
    assert data["slug"] == "lozenets"
    assert data["name"] == "Лозенец"
    assert data["lat"] == pytest.approx(42.66)


def test_prices_by_type_and_transaction_type(client):
    sale = client.get("/api/neighbourhoods/lozenets/prices?transaction_type=sale").json()
    assert "двустаен" in sale["by_type"]
    # latest двустаен sale point carries price_eur + price_eur_sqm
    last = sale["by_type"]["двустаен"][-1]
    assert last["price_eur"] == pytest.approx(204000)
    assert last["price_eur_sqm"] == pytest.approx(3400)

    rent = client.get("/api/neighbourhoods/lozenets/prices?transaction_type=rent").json()
    assert rent["transaction_type"] == "rent"
    assert rent["by_type"]["двустаен"][-1]["price_eur"] == pytest.approx(700)
    # sale series must not leak into rent
    assert rent["series"][-1]["price_eur_sqm"] == pytest.approx(11)


def test_neighbours_directional(client):
    data = client.get("/api/neighbourhoods/lozenets/neighbours").json()
    assert len(data) >= 1
    izg = next(d for d in data if d["slug"] == "izgrev")
    assert izg["direction"] == "NE"      # izgrev is north-east of lozenets
    assert izg["distance_m"] > 0
    assert isinstance(izg["series"], list)


def test_reference_endpoints(client):
    gold = client.get("/api/reference/gold").json()
    assert gold[-1]["price_eur_per_gram"] == pytest.approx(80.0)
    wage = client.get("/api/reference/min-wage").json()
    assert wage[-1]["year"] == 2025
    assert wage[-1]["amount_bgn"] == pytest.approx(1077.0)
