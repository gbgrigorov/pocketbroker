"""ETL loader: raw imot.bg JSONL -> relational tables.

Loads only the MVP-mapped neighbourhoods (those in the canonical registry). Every
input row is accounted for in the returned LoadReport — loaded or skipped, never
silently dropped.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, Iterable, Optional

from app.models import City, GoldPrice, MinWage, Neighbourhood, PriceSnapshot
from etl.neighbourhoods import NameResolver

SOFIA = ("София", "sofia")

_PRICE_FIELDS = ("price_eur", "price_eur_sqm", "overall_avg_eur_sqm")


@dataclass
class LoadReport:
    neighbourhoods_loaded: int = 0
    current_loaded: int = 0
    current_skipped: int = 0
    history_loaded: int = 0
    history_skipped: int = 0
    gold_loaded: int = 0
    min_wage_loaded: int = 0


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    return date.fromisoformat(value)


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _price_snapshot(neighbourhood_id: int, rec: dict) -> PriceSnapshot:
    return PriceSnapshot(
        neighbourhood_id=neighbourhood_id,
        source=rec.get("source"),
        property_type=rec.get("property_type"),
        transaction_type=rec.get("transaction_type", "sale"),
        period_date=_parse_date(rec.get("period_date")),
        scraped_at=_parse_dt(rec.get("scraped_at")),
        **{f: rec.get(f) for f in _PRICE_FIELDS},
    )


def load_all(
    session,
    *,
    registry: Dict[str, dict],
    current_records: Iterable[dict],
    history_records: Iterable[dict],
    resolver: NameResolver,
    gold_records: Iterable[dict] = (),
    min_wage_records: Iterable[dict] = (),
) -> LoadReport:
    report = LoadReport()

    city = City(name=SOFIA[0], slug=SOFIA[1])
    session.add(city)
    session.flush()

    slug_to_id: Dict[str, int] = {}
    for entry in registry.values():
        n = Neighbourhood(
            city_id=city.id,
            name=entry["name"],
            slug=entry["slug"],
            lat=entry.get("lat"),
            lon=entry.get("lon"),
            coord_source=entry.get("coord_source"),
        )
        session.add(n)
        session.flush()
        slug_to_id[entry["slug"]] = n.id
        report.neighbourhoods_loaded += 1

    # Current snapshot already carries slugs
    for rec in current_records:
        nid = slug_to_id.get(rec.get("neighborhood_slug"))
        if nid is None:
            report.current_skipped += 1
            continue
        session.add(_price_snapshot(nid, rec))
        report.current_loaded += 1

    # Historical rows have no slug — resolve by name
    for rec in history_records:
        slug = resolver.resolve(rec.get("neighborhood"))
        nid = slug_to_id.get(slug) if slug else None
        if nid is None:
            report.history_skipped += 1
            continue
        session.add(_price_snapshot(nid, rec))
        report.history_loaded += 1

    # Reference series (standalone tables, no neighbourhood FK)
    for rec in gold_records:
        session.add(GoldPrice(
            period_date=_parse_date(rec.get("period_date")),
            price_eur_per_gram=rec.get("price_eur_per_gram"),
            source=rec.get("source"),
        ))
        report.gold_loaded += 1

    for rec in min_wage_records:
        session.add(MinWage(
            year=rec.get("year"),
            amount_bgn=rec.get("amount_bgn"),
            amount_eur=rec.get("amount_eur"),
            source=rec.get("source"),
        ))
        report.min_wage_loaded += 1

    session.commit()
    return report
