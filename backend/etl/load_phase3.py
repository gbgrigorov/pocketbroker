"""Phase-3 ETL loaders — normalized builders / new buildings / crawl telemetry -> DB.

All loaders are idempotent (upsert on a natural key), so the pipeline is safe to
re-run on a schedule:

- builders          : upsert on ``builder.eik``
- new buildings     : upsert on ``new_building.canonical_key``; child
                      ``new_building_source`` rows are replaced each load
- crawl runs        : dedupe on ``(site, scope, started_at)``

This runs *after* the price ETL has populated ``city`` and ``neighbourhood``
(the FKs new_building depends on).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, Iterable, Optional

from sqlalchemy import select

from app.models import Builder, City, CrawlRun, Neighbourhood, NewBuilding, NewBuildingSource
from app.names import norm_name as _norm_name  # noqa: F401 — re-exported


@dataclass
class Phase3Report:
    builders_upserted: int = 0
    new_buildings_upserted: int = 0
    new_building_sources: int = 0
    projects_linked_to_builder: int = 0
    crawl_runs_loaded: int = 0
    crawl_runs_skipped: int = 0


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    return date.fromisoformat(value[:10])


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


# --- builders ---------------------------------------------------------------

def load_builders(session, records: Iterable[dict], report: Phase3Report) -> None:
    from etl.entities import entity_for_builder  # deferred: avoids import cycle
    for rec in records:
        eik = rec.get("eik")
        if not eik:
            continue
        builder = session.scalar(select(Builder).where(Builder.eik == eik))
        if builder is None:
            builder = Builder(eik=eik)
            session.add(builder)
        builder.name = rec.get("name") or builder.name or eik
        builder.legal_form = rec.get("legal_form")
        builder.address = rec.get("address")
        builder.capital_bgn = rec.get("capital_bgn")
        builder.status = rec.get("status")
        builder.financials = rec.get("financials")
        builder.ksb_category = rec.get("ksb_category")
        builder.ksb_active = rec.get("ksb_active")
        builder.insolvency_flag = rec.get("insolvency_flag")
        builder.tax_debt_bgn = rec.get("tax_debt_bgn")
        builder.last_checked_at = _parse_dt(rec.get("last_checked_at"))
        session.flush()  # assign builder.id before mirroring into the graph
        entity_for_builder(session, builder)  # Phase 3.5: back each builder with a node
        report.builders_upserted += 1
    session.flush()


# --- new buildings ----------------------------------------------------------

def _builder_index(session) -> Dict[str, int]:
    """Map normalized builder name -> builder.id for developer linking."""
    index: Dict[str, int] = {}
    for bid, name in session.execute(select(Builder.id, Builder.name)):
        key = _norm_name(name)
        if key:
            index.setdefault(key, bid)
    return index


def load_new_buildings(session, records: Iterable[dict], city_slug: str,
                       report: Phase3Report) -> None:
    city = session.scalar(select(City).where(City.slug == city_slug))
    if city is None:
        raise SystemExit(
            f"City '{city_slug}' not found — run the price ETL first to populate city/neighbourhood."
        )
    nbhd_by_slug = {
        slug: nid
        for nid, slug in session.execute(
            select(Neighbourhood.id, Neighbourhood.slug).where(Neighbourhood.city_id == city.id)
        )
    }
    builder_index = _builder_index(session)

    for rec in records:
        key = rec.get("canonical_key")
        if not key:
            continue
        nb = session.scalar(select(NewBuilding).where(NewBuilding.canonical_key == key))
        if nb is None:
            nb = NewBuilding(canonical_key=key, city_id=city.id)
            session.add(nb)
        nb.name = rec.get("name") or key
        nb.neighbourhood_id = nbhd_by_slug.get(rec.get("neighborhood_slug"))
        nb.developer_name = rec.get("developer_name")
        dev_id = builder_index.get(_norm_name(rec.get("developer_name")))
        nb.developer_id = dev_id
        if dev_id:
            report.projects_linked_to_builder += 1
        nb.akt_stage = rec.get("akt_stage")
        nb.completion_year = rec.get("completion_year")
        nb.floors = rec.get("floors")
        nb.materials = rec.get("materials")
        nb.price_eur_sqm = rec.get("price_eur_sqm")
        nb.area_min_sqm = rec.get("area_min_sqm")
        nb.area_max_sqm = rec.get("area_max_sqm")
        nb.first_seen = _parse_date(rec.get("first_seen"))
        nb.last_seen = _parse_date(rec.get("last_seen"))
        session.flush()  # ensure nb.id for sources

        # Replace child source rows (full refresh of the audit trail).
        for old in list(nb.sources):
            session.delete(old)
        for src in rec.get("sources", []):
            session.add(NewBuildingSource(
                new_building_id=nb.id,
                site=src.get("site") or "?",
                source_name=src.get("source_name"),
                url=src.get("url"),
                price_eur_sqm=src.get("price_eur_sqm"),
                scraped_at=_parse_dt(src.get("scraped_at")),
            ))
            report.new_building_sources += 1
        report.new_buildings_upserted += 1
    session.flush()


# --- crawl telemetry --------------------------------------------------------

def load_crawl_runs(session, manifests: Iterable[dict], city_slug_to_id: Dict[str, int],
                    report: Phase3Report) -> None:
    for m in manifests:
        started = _parse_dt(m.get("started_at"))
        site, scope = m.get("site"), m.get("scope")
        exists = session.scalar(
            select(CrawlRun.id).where(
                CrawlRun.site == site, CrawlRun.scope == scope, CrawlRun.started_at == started
            )
        )
        if exists:
            report.crawl_runs_skipped += 1
            continue
        session.add(CrawlRun(
            domain=m.get("domain") or "?",
            site=site or "?",
            scope=scope,
            city_id=city_slug_to_id.get(scope),
            pages_fetched=m.get("pages_fetched", 0),
            bytes_downloaded=m.get("bytes_downloaded", 0),
            records_parsed=m.get("records_parsed", 0),
            records_emitted=m.get("records_emitted", 0),
            errors=m.get("errors", 0),
            duration_s=m.get("duration_s"),
            started_at=started,
        ))
        report.crawl_runs_loaded += 1
    session.flush()
