import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import City, Neighbourhood, PriceSnapshot
from etl.load import load_all
from etl.neighbourhoods import NameResolver


@pytest.fixture
def session():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    s = Session()
    yield s
    s.close()


@pytest.fixture
def fixtures():
    registry = {
        "lozenets": {"slug": "lozenets", "name": "Лозенец", "lat": 42.66, "lon": 23.32, "coord_source": "nominatim"},
    }
    current_records = [
        {"neighborhood": "Лозенец", "neighborhood_slug": "lozenets", "property_type": "двустаен",
         "transaction_type": "rent",
         "price_eur": 180000.0, "price_bgn": 352050.0, "price_eur_sqm": 3450.0, "price_bgn_sqm": 6747.0,
         "overall_avg_eur_sqm": 3200.0, "period_date": "2026-05-01", "source": "imot.bg",
         "scraped_at": "2026-05-26T08:52:44.932151Z"},
        {"neighborhood": "Лозенец", "neighborhood_slug": "lozenets", "property_type": "тристаен",
         "price_eur": 250000.0, "price_bgn": 488958.0, "price_eur_sqm": 3500.0, "price_bgn_sqm": 6845.0,
         "overall_avg_eur_sqm": 3200.0, "period_date": "2026-05-01", "source": "imot.bg",
         "scraped_at": "2026-05-26T08:52:44.932151Z"},
        {"neighborhood": "Без координати", "neighborhood_slug": "no-coords", "property_type": "двустаен",
         "price_eur": 90000.0, "price_bgn": 176025.0, "price_eur_sqm": 1500.0, "price_bgn_sqm": 2934.0,
         "overall_avg_eur_sqm": 1500.0, "period_date": "2026-05-01", "source": "imot.bg",
         "scraped_at": "2026-05-26T08:52:44.932151Z"},
    ]
    history_records = [
        {"neighborhood": "ЛОЗЕНЕЦ", "neighborhood_slug": None, "property_type": "едностаен",
         "price_eur": 14937.0, "price_bgn": 29214.0, "price_eur_sqm": 262.0, "price_bgn_sqm": 512.0,
         "overall_avg_eur_sqm": 301.0, "period_date": "1995-10-14", "source": "imot.bg",
         "scraped_at": "2026-05-26T08:51:08.471634Z"},
        {"neighborhood": "Бъкстон", "neighborhood_slug": None, "property_type": "едностаен",
         "price_eur": 10000.0, "price_bgn": 19558.0, "price_eur_sqm": 200.0, "price_bgn_sqm": 391.0,
         "overall_avg_eur_sqm": 200.0, "period_date": "1995-10-14", "source": "imot.bg",
         "scraped_at": "2026-05-26T08:51:08.471634Z"},
    ]
    resolver = NameResolver({e["name"]: s for s, e in registry.items()})
    return registry, current_records, history_records, resolver


def test_seeds_one_city_and_registry_neighbourhoods(session, fixtures):
    registry, current, history, resolver = fixtures
    load_all(session, registry=registry, current_records=current,
             history_records=history, resolver=resolver)
    assert session.scalar(select(func.count()).select_from(City)) == 1
    assert session.scalar(select(func.count()).select_from(Neighbourhood)) == 1


def test_loads_only_mapped_price_rows(session, fixtures):
    registry, current, history, resolver = fixtures
    load_all(session, registry=registry, current_records=current,
             history_records=history, resolver=resolver)
    # 2 current lozenets + 1 history lozenets = 3; no-coords + Бъкстон excluded
    assert session.scalar(select(func.count()).select_from(PriceSnapshot)) == 3


def test_report_conserves_every_input_row(session, fixtures):
    registry, current, history, resolver = fixtures
    report = load_all(session, registry=registry, current_records=current,
                      history_records=history, resolver=resolver)
    assert report.current_loaded == 2
    assert report.current_skipped == 1
    assert report.history_loaded == 1
    assert report.history_skipped == 1
    # conservation: nothing vanishes silently
    assert report.current_loaded + report.current_skipped == len(current)
    assert report.history_loaded + report.history_skipped == len(history)


def test_price_row_links_to_correct_neighbourhood(session, fixtures):
    registry, current, history, resolver = fixtures
    load_all(session, registry=registry, current_records=current,
             history_records=history, resolver=resolver)
    n = session.scalar(select(Neighbourhood).where(Neighbourhood.slug == "lozenets"))
    assert len(n.prices) == 3


def test_transaction_type_defaults_to_sale_and_respects_rent(session, fixtures):
    registry, current, history, resolver = fixtures
    load_all(session, registry=registry, current_records=current,
             history_records=history, resolver=resolver)
    rows = session.scalars(select(PriceSnapshot)).all()
    kinds = sorted({r.transaction_type for r in rows})
    # one current lozenets row is tagged rent; everything else defaults to sale
    assert kinds == ["rent", "sale"]


def test_model_has_no_bgn_columns():
    assert not hasattr(PriceSnapshot, "price_bgn")
    assert not hasattr(PriceSnapshot, "price_bgn_sqm")


def test_same_slug_allowed_across_cities(session):
    """imot.bg reuses slugs across cities — the (city_id, slug) constraint must allow it."""
    sofia = City(name="София", slug="sofia")
    varna = City(name="Варна", slug="varna")
    session.add_all([sofia, varna])
    session.flush()
    session.add(Neighbourhood(city_id=sofia.id, name="Център", slug="tsentar"))
    session.add(Neighbourhood(city_id=varna.id, name="Център", slug="tsentar"))
    session.commit()  # must NOT raise — same slug, different city
    assert session.scalar(select(func.count()).select_from(Neighbourhood)) == 2


def test_duplicate_slug_within_city_rejected(session):
    """The composite constraint still forbids a duplicate slug inside one city."""
    from sqlalchemy.exc import IntegrityError

    sofia = City(name="София", slug="sofia")
    session.add(sofia)
    session.flush()
    session.add(Neighbourhood(city_id=sofia.id, name="Център", slug="tsentar"))
    session.add(Neighbourhood(city_id=sofia.id, name="Центъра", slug="tsentar"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_loads_gold_and_min_wage(session, fixtures):
    from app.models import GoldPrice, MinWage
    registry, current, history, resolver = fixtures
    gold = [{"period_date": "2020-10-01", "price_eur_per_gram": 50.0, "source": "x"}]
    wage = [{"year": 2020, "amount_bgn": 610.0, "amount_eur": 311.0, "source": "y"}]
    report = load_all(session, registry=registry, current_records=current,
                      history_records=history, resolver=resolver,
                      gold_records=gold, min_wage_records=wage)
    assert report.gold_loaded == 1 and report.min_wage_loaded == 1
    assert session.scalar(select(func.count()).select_from(GoldPrice)) == 1
    assert session.scalar(select(func.count()).select_from(MinWage)) == 1
