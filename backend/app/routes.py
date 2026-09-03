"""API routes: bubble-map metric, per-neighbourhood prices (sale/rent),
directional neighbours for the deep-dive cluster, and reference series."""

from __future__ import annotations

import math
import os
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app import captcha, pricing
from app.auth import (can_view, current_superuser, current_user,
                      current_user_optional, scrub)
from app.coverage import coverage_flags
from app.db import get_session
from app.models import (Builder, City, CrawlRun, Entity, EntityEdge,
                        EntitySignal, GoldPrice, MinWage, Neighbourhood,
                        NeighbourhoodAir, NewBuilding, NewBuildingSource,
                        PriceSnapshot, ResearchRequest, User)
from app.schemas import (AdminResearchRequestRead, AdminUserRead,
                         CourtResearchOrderCreate, CourtResearchOrderRead,
                         ResearchRequestCreate, ResearchRequestRead)

router = APIRouter(prefix="/api")


def _f(value) -> Optional[float]:
    return float(value) if value is not None else None


def _overall_series(n: Neighbourhood, transaction_type: str):
    """Sorted [{period_date, price_eur_sqm}] of overall avg €/m² for one txn type."""
    by_period = {}
    for p in n.prices:
        if (p.transaction_type == transaction_type and p.period_date is not None
                and p.overall_avg_eur_sqm is not None):
            by_period[p.period_date] = _f(p.overall_avg_eur_sqm)
    return [{"period_date": d.isoformat(), "price_eur_sqm": v}
            for d, v in sorted(by_period.items())]


def _overall_at(n: Neighbourhood, txn: str, year: Optional[int]) -> Optional[float]:
    """Latest-period overall avg €/m² for one txn type (optionally within a year)."""
    rows = [p for p in n.prices if p.period_date is not None
            and (p.transaction_type or "sale") == txn
            and (year is None or p.period_date.year == year)]
    if not rows:
        return None
    latest = max(p.period_date for p in rows)
    vals = [_f(p.overall_avg_eur_sqm) for p in rows
            if p.period_date == latest and p.overall_avg_eur_sqm is not None]
    return sum(vals) / len(vals) if vals else None


def _overall_by_year(n: Neighbourhood, txn: str) -> tuple[dict[str, float], Optional[float]]:
    """All years' overall avg €/m² for one txn type, computed in a single pass.

    Returns ``({ "2025": 1830.0, ... }, latest)`` where each year's value is the
    latest-period-within-that-year average (same rule as ``_overall_at``) and
    ``latest`` is the value at the most recent period across all years (the
    "Latest" view). Lets the frontend hold every year and filter client-side, so
    the slider never refetches. Years with no priced data are simply absent.
    """
    # year -> {period_date -> [values at that period]}
    buckets: dict[int, dict] = {}
    for p in n.prices:
        if (p.period_date is None or (p.transaction_type or "sale") != txn
                or p.overall_avg_eur_sqm is None):
            continue
        buckets.setdefault(p.period_date.year, {}).setdefault(
            p.period_date, []).append(_f(p.overall_avg_eur_sqm))

    by_year: dict[str, float] = {}
    latest_period = None
    latest_val = None
    for year, periods in buckets.items():
        newest = max(periods)
        vals = periods[newest]
        by_year[str(year)] = sum(vals) / len(vals)
        if latest_period is None or newest > latest_period:
            latest_period, latest_val = newest, by_year[str(year)]
    return by_year, latest_val


def _air_by_neighbourhood(session) -> dict[int, dict]:
    """All seasonal air rows folded into {neighbourhood_id: {year: {season: {...}}}}.

    Built in one query (no N+1) and attached to /map features. Each season carries
    pm25/aqi plus the sensor_count that fed the average (a confidence hint). Shape:
        { 12: { "2024": { "winter": {"pm25": 24.1, "aqi": 76, "n": 9},
                          "summer": {"pm25": 9.2,  "aqi": 38, "n": 9} }, ... } }
    """
    out: dict[int, dict] = {}
    for row in session.scalars(select(NeighbourhoodAir)).all():
        year = out.setdefault(row.neighbourhood_id, {}).setdefault(str(row.year), {})
        year[row.season] = {
            "pm25": _f(row.pm25_avg),
            "aqi": _f(row.aqi_avg),
            "n": row.sensor_count,
        }
    return out


# ---------------------------------------------------------------------------
# In-memory caches for the (essentially static, monthly-refreshed) map data,
# plus the entity browse list (static between ETL runs, hammered by type-ahead).
# Keyed by city slug for /map ("__all__" = no-city); a single entry for /cities.
# Cleared by clear_caches() — call POST /api/admin/refresh-cache after an ETL run,
# or just restart the service (deploy already does). See HANDOVER / RUNBOOK.
# ---------------------------------------------------------------------------
_map_cache: dict[str, list] = {}
_cities_cache: Optional[list] = None
_entities_cache: Optional[list] = None  # pre-sorted rows for /entities
_entity_signal_counts_cache: Optional[dict] = None  # id -> tier counts (list semantics)
_graph_cache: dict[int, dict] = {}  # limit -> /graph payload (~250ms of DB work each)
# ``limit`` is caller-supplied (1..2000) and each payload is ~1MB at the top end,
# so the graph cache is bounded and evicts oldest-first — otherwise walking the
# limit range would pin gigabytes. In practice only 500 (default) and 2000 (the
# entity browse page) are ever requested.
_GRAPH_CACHE_MAX = 4


def clear_caches() -> None:
    """Drop all cached payloads so the next request recomputes."""
    global _cities_cache, _entities_cache, _entity_signal_counts_cache
    _map_cache.clear()
    _graph_cache.clear()
    _cities_cache = None
    _entities_cache = None
    _entity_signal_counts_cache = None


def _city_air(session) -> dict[str, dict]:
    """City-level air for the country pins: {city_slug: {winter:{pm25,aqi}, summer:{...}}}.

    Uses each city's *latest* air year and averages its neighbourhoods per season.
    The country map has no season toggle, so the pin picks one client-side.
    """
    rows = session.execute(
        select(City.slug, NeighbourhoodAir.year, NeighbourhoodAir.season,
               NeighbourhoodAir.pm25_avg, NeighbourhoodAir.aqi_avg)
        .join(Neighbourhood, Neighbourhood.id == NeighbourhoodAir.neighbourhood_id)
        .join(City, City.id == Neighbourhood.city_id)
    ).all()

    # city -> latest year seen
    latest: dict[str, int] = {}
    for slug, year, *_ in rows:
        latest[slug] = max(year, latest.get(slug, year))

    # city -> season -> [pm25...], [aqi...]  (latest year only)
    acc: dict[str, dict] = {}
    for slug, year, season, pm25, aqi in rows:
        if year != latest[slug]:
            continue
        s = acc.setdefault(slug, {}).setdefault(season, {"pm25": [], "aqi": []})
        if pm25 is not None:
            s["pm25"].append(float(pm25))
        if aqi is not None:
            s["aqi"].append(float(aqi))

    out: dict[str, dict] = {}
    for slug, seasons in acc.items():
        out[slug] = {
            season: {
                "pm25": round(sum(v["pm25"]) / len(v["pm25"]), 1) if v["pm25"] else None,
                "aqi": round(sum(v["aqi"]) / len(v["aqi"])) if v["aqi"] else None,
            }
            for season, v in seasons.items()
        }
    return out


def _resolve_neighbourhood(session, slug: str, city: Optional[str]) -> Optional[Neighbourhood]:
    """Find a neighbourhood by slug. Slugs are unique only *within* a city
    (every city has a "tsentar"), so when ``city`` is given we constrain on it;
    without it we fall back to the first match (legacy single-city behaviour)."""
    stmt = select(Neighbourhood).where(Neighbourhood.slug == slug)
    if city is not None:
        stmt = stmt.join(City).where(City.slug == city)
    return session.scalar(stmt)


@router.get("/cities")
def get_cities(session=Depends(get_session)):
    """Available cities for the country map — one clickable pin each.

    ``lat``/``lon`` is the centroid of the city's mapped neighbourhoods (used to
    place the pin); ``avg_eur_sqm`` is the mean of their latest overall sale €/m².
    Cities with no mapped neighbourhoods are skipped. Ordered busiest-first.
    Cached in memory (see ``clear_caches``); year-independent.
    """
    global _cities_cache
    if _cities_cache is not None:
        return _cities_cache

    # Eager-load neighbourhoods + their prices in two queries instead of N+1.
    stmt = select(City).options(
        selectinload(City.neighbourhoods).selectinload(Neighbourhood.prices))
    city_air = _city_air(session)
    out = []
    for c in session.scalars(stmt).all():
        coords = [(float(n.lat), float(n.lon)) for n in c.neighbourhoods
                  if n.lat is not None and n.lon is not None]
        if not coords:
            continue
        avgs = [v for v in (_overall_at(n, "sale", None) for n in c.neighbourhoods)
                if v is not None]
        out.append({
            "slug": c.slug, "name": c.name,
            "lat": sum(la for la, _ in coords) / len(coords),
            "lon": sum(lo for _, lo in coords) / len(coords),
            "neighbourhood_count": len(coords),
            "avg_eur_sqm": sum(avgs) / len(avgs) if avgs else None,
            "air": city_air.get(c.slug) or None,
        })
    out.sort(key=lambda c: c["neighbourhood_count"], reverse=True)
    _cities_cache = out
    return out


@router.get("/map")
def get_map(city: Optional[str] = None, session=Depends(get_session)):
    """Mapped neighbourhoods + overall sale & rent €/m² for **every year**.

    The frontend fetches this once per city and holds all years in memory, so the
    year slider and the metric switch (price vs price-to-rent, computed client-side
    from sale ÷ rent) both filter locally with no refetch. Each feature carries:

      ``latest``  → {sale, rent} at the most recent period (the "Latest" view)
      ``by_year`` → {sale, rent} per year, e.g. {"2025": {...}, ...}

    Passing ``city`` (slug) restricts the field to a single city's bubbles.
    Result is cached in memory per city (see ``clear_caches``).
    """
    key = city or "__all__"
    if key in _map_cache:
        return _map_cache[key]

    # Eager-load every neighbourhood's prices in one extra query (no N+1).
    stmt = select(Neighbourhood).options(selectinload(Neighbourhood.prices))
    if city is not None:
        stmt = stmt.join(City).where(City.slug == city)

    air_by_nbhd = _air_by_neighbourhood(session)

    features = []
    for n in session.scalars(stmt).all():
        sale_by_year, sale_latest = _overall_by_year(n, "sale")
        rent_by_year, rent_latest = _overall_by_year(n, "rent")
        by_year = {
            y: {"sale": sale_by_year.get(y), "rent": rent_by_year.get(y)}
            for y in (sale_by_year.keys() | rent_by_year.keys())
        }
        features.append({
            "slug": n.slug, "name": n.name,
            "lat": _f(n.lat), "lon": _f(n.lon),
            "latest": {"sale": sale_latest, "rent": rent_latest},
            "by_year": by_year,
            "air": air_by_nbhd.get(n.id) or None,
        })
    _map_cache[key] = features
    return features


@router.post("/admin/refresh-cache")
def refresh_cache(x_admin_token: str = Header(default="")):
    """Clear the in-memory /map + /cities caches after a DB/ETL update.

    Guarded by the ``ADMIN_TOKEN`` env var; fails closed when it is unset so the
    endpoint can never be hit on a misconfigured deploy. A plain service restart
    clears the cache too (deploy already restarts), so this is the no-redeploy path.
    """
    expected = os.environ.get("ADMIN_TOKEN")
    if not expected or x_admin_token != expected:
        raise HTTPException(status_code=403, detail="forbidden")
    clear_caches()
    return {"status": "ok", "cleared": True}


@router.get("/neighbourhoods/{slug}")
def get_neighbourhood(slug: str, city: Optional[str] = None, session=Depends(get_session)):
    """Single neighbourhood metadata (+ per-year seasonal air, when available)."""
    n = _resolve_neighbourhood(session, slug, city)
    if n is None:
        raise HTTPException(status_code=404, detail=f"Unknown neighbourhood: {slug}")
    return {"slug": n.slug, "name": n.name, "district": n.district,
            "lat": _f(n.lat), "lon": _f(n.lon),
            "air": _air_by_year(session, n.id)}


def _air_by_year(session, neighbourhood_id: int) -> Optional[dict]:
    """All seasonal air years for one neighbourhood, so the single-page table can
    track the year slider. Same shape as a /map feature's `air`:
        {"2024": {"winter": {"pm25":..,"aqi":..,"n":..}, "summer": {...}}, ...}
    None when the neighbourhood has no air rows."""
    rows = session.scalars(
        select(NeighbourhoodAir)
        .where(NeighbourhoodAir.neighbourhood_id == neighbourhood_id)
    ).all()
    if not rows:
        return None
    out: dict[str, dict] = {}
    for r in rows:
        out.setdefault(str(r.year), {})[r.season] = {
            "pm25": _f(r.pm25_avg), "aqi": _f(r.aqi_avg), "n": r.sensor_count,
        }
    return out


@router.get("/neighbourhoods/{slug}/prices")
def get_prices(
    slug: str,
    transaction_type: str = Query("sale", pattern="^(sale|rent)$"),
    city: Optional[str] = None,
    session=Depends(get_session),
):
    """Overall €/m² series + per-room-type series for one neighbourhood + txn type.

    `series`  → overall avg €/m², one point per period (backwards compatible).
    `by_type` → {property_type: [{period_date, price_eur, price_eur_sqm}]}.
    """
    n = _resolve_neighbourhood(session, slug, city)
    if n is None:
        raise HTTPException(status_code=404, detail=f"Unknown neighbourhood: {slug}")

    by_type: dict[str, dict] = {}
    for p in n.prices:
        if (p.transaction_type or "sale") != transaction_type or p.period_date is None:
            continue
        if p.property_type:
            bucket = by_type.setdefault(p.property_type, {})
            bucket[p.period_date] = {
                "period_date": p.period_date.isoformat(),
                "price_eur": _f(p.price_eur),
                "price_eur_sqm": _f(p.price_eur_sqm),
            }
    by_type_sorted = {pt: [rows[d] for d in sorted(rows)] for pt, rows in by_type.items()}

    return {
        "slug": n.slug, "name": n.name, "transaction_type": transaction_type,
        "series": _overall_series(n, transaction_type),
        "by_type": by_type_sorted,
    }


def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


_SECTORS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def _sector(bearing: float) -> str:
    """Compass bearing (0=N, clockwise) → one of 8 sectors."""
    return _SECTORS[int(((bearing + 22.5) % 360) // 45)]


@router.get("/neighbourhoods/{slug}/neighbours")
def get_neighbours(slug: str, city: Optional[str] = None, session=Depends(get_session)):
    """Nearest neighbour in each of 8 compass sectors (computed from lat/lon).

    Each item carries the neighbour's overall sale €/m² series so the cluster can
    size bubbles per selected year. Center neighbourhood is excluded; candidates
    are restricted to the same city so a ring never crosses city boundaries.
    """
    center = _resolve_neighbourhood(session, slug, city)
    if center is None:
        raise HTTPException(status_code=404, detail=f"Unknown neighbourhood: {slug}")
    if center.lat is None or center.lon is None:
        return []

    clat, clon = float(center.lat), float(center.lon)
    best: dict[str, dict] = {}  # sector -> {dist, neighbour}
    candidates = select(Neighbourhood).where(Neighbourhood.city_id == center.city_id)
    for n in session.scalars(candidates).all():
        if n.id == center.id or n.lat is None or n.lon is None:
            continue
        nlat, nlon = float(n.lat), float(n.lon)
        dist = _haversine_m(clat, clon, nlat, nlon)
        # bearing from center to neighbour
        dlon = math.radians(nlon - clon)
        y = math.sin(dlon) * math.cos(math.radians(nlat))
        x = (math.cos(math.radians(clat)) * math.sin(math.radians(nlat))
             - math.sin(math.radians(clat)) * math.cos(math.radians(nlat)) * math.cos(dlon))
        bearing = (math.degrees(math.atan2(y, x)) + 360) % 360
        sec = _sector(bearing)
        if sec not in best or dist < best[sec]["dist"]:
            best[sec] = {"dist": dist, "neighbour": n}

    out = []
    for sec, item in best.items():
        n = item["neighbour"]
        out.append({
            "slug": n.slug, "name": n.name, "direction": sec,
            "distance_m": int(item["dist"]),
            "lat": _f(n.lat), "lon": _f(n.lon),
            "series": _overall_series(n, "sale"),
        })
    return out


# --- Phase 3: stats counter, builders, new-building projects ----------------


@router.get("/stats")
def get_stats(session=Depends(get_session)):
    """Headline crawl counter — 'how much data have we processed' flex number.

    Sums all recorded crawl runs and counts the entities we've assembled.
    """
    agg = session.execute(select(
        func.coalesce(func.sum(CrawlRun.pages_fetched), 0),
        func.coalesce(func.sum(CrawlRun.bytes_downloaded), 0),
        func.coalesce(func.sum(CrawlRun.records_emitted), 0),
        func.coalesce(func.count(CrawlRun.id), 0),
        func.max(CrawlRun.started_at),
    )).one()
    pages, num_bytes, records, runs, last_run = agg
    num_bytes = int(num_bytes or 0)

    builders = session.scalar(select(func.count(Builder.id))) or 0
    projects = session.scalar(select(func.count(NewBuilding.id))) or 0
    cities = session.scalar(select(func.count(func.distinct(CrawlRun.scope)))) or 0
    sites = session.scalar(select(func.count(func.distinct(CrawlRun.site)))) or 0

    return {
        "data_scanned_bytes": num_bytes,
        "data_scanned_mb": round(num_bytes / 1e6, 2),
        "data_scanned_gb": round(num_bytes / 1e9, 4),
        "data_points": int(records or 0),
        "pages_fetched": int(pages or 0),
        "crawl_runs": int(runs or 0),
        "builders": int(builders),
        "projects": int(projects),
        "scopes": int(cities),
        "sites": int(sites),
        "last_run": last_run.isoformat() if last_run else None,
        "counts": {
            "price_snapshots": session.scalar(select(func.count(PriceSnapshot.id))) or 0,
            "entities":        session.scalar(select(func.count(Entity.id))) or 0,
            "ownership_links": session.scalar(select(func.count(EntityEdge.id))) or 0,
            "builders":        int(builders),
            "neighbourhoods":  session.scalar(select(func.count(Neighbourhood.id))) or 0,
            "signals":         session.scalar(select(func.count(EntitySignal.id))) or 0,
            "gold_prices":     session.scalar(select(func.count(GoldPrice.id))) or 0,
            "min_wages":       session.scalar(select(func.count(MinWage.id))) or 0,
            "projects":        int(projects),
            "cities":          session.scalar(select(func.count(City.id))) or 0,
        },
    }


def _builder_summary(b: Builder) -> dict:
    return {
        "eik": b.eik, "name": b.name, "legal_form": b.legal_form,
        "status": b.status, "ksb_category": b.ksb_category, "ksb_active": b.ksb_active,
        "insolvency_flag": b.insolvency_flag, "tax_debt_bgn": _f(b.tax_debt_bgn),
        "capital_bgn": _f(b.capital_bgn),
    }


@router.get("/builders")
def list_builders(
    q: Optional[str] = Query(None, description="name/ЕИК substring"),
    insolvent: Optional[bool] = None,
    has_tax_debt: Optional[bool] = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    session=Depends(get_session),
):
    """Paginated builder list with trust-signal filters."""
    stmt = select(Builder)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Builder.name.ilike(like) | Builder.eik.ilike(like))
    if insolvent is not None:
        stmt = stmt.where(Builder.insolvency_flag.is_(insolvent))
    if has_tax_debt is True:
        stmt = stmt.where(Builder.tax_debt_bgn.is_not(None), Builder.tax_debt_bgn > 0)
    total = session.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = session.scalars(stmt.order_by(Builder.name).limit(limit).offset(offset)).all()
    return {"total": total, "limit": limit, "offset": offset,
            "items": [_builder_summary(b) for b in rows]}


def _edge_party(edge: EntityEdge, e: Entity) -> dict:
    """One end of an edge as a list item (key = eik for companies, person_key for persons)."""
    return {
        "name": e.name, "eik": e.eik, "person_key": e.person_key, "kind": e.kind,
        "key": e.eik or e.person_key, "slug": e.slug, "is_builder": bool(e.is_builder),
        "share_pct": _f(edge.share_pct), "role": edge.role, "is_current": edge.is_current,
    }


def _incoming_edges(session, entity_id: Optional[int], relation: str):
    """Entities connected *into* ``entity_id`` by ``relation`` (its owners/managers)."""
    if entity_id is None:
        return []
    stmt = (
        select(EntityEdge, Entity)
        .join(Entity, Entity.id == EntityEdge.src_entity_id)
        .where(EntityEdge.dst_entity_id == entity_id, EntityEdge.relation == relation)
    )
    return [_edge_party(edge, e) for edge, e in session.execute(stmt)]


def _outgoing_edges(session, entity_id: Optional[int], relation: str):
    """Entities ``entity_id`` connects *out to* by ``relation`` (what it owns/manages)."""
    if entity_id is None:
        return []
    stmt = (
        select(EntityEdge, Entity)
        .join(Entity, Entity.id == EntityEdge.dst_entity_id)
        .where(EntityEdge.src_entity_id == entity_id, EntityEdge.relation == relation)
    )
    return [_edge_party(edge, e) for edge, e in session.execute(stmt)]


# --- problematic-developer signals (evidence aggregator, not a verdict) ------

_TIER_ORDER = {"official": 0, "community": 1, "web": 2}


def _signal_subject_ids(session, entity_id: Optional[int]) -> dict:
    """Entities whose signals count toward ``entity_id``: itself + the people who
    own/manage it. Maps id -> a "via" label (None for the entity itself), so a
    flag found on a manager is shown as "via управител <name>"."""
    out: dict = {}
    if entity_id is None:
        return out
    out[entity_id] = None
    stmt = (
        select(Entity.id, Entity.name, EntityEdge.relation)
        .join(EntityEdge, Entity.id == EntityEdge.src_entity_id)
        .where(EntityEdge.dst_entity_id == entity_id,
               EntityEdge.relation.in_(("ownership", "management")),
               Entity.kind == "person")
    )
    for pid, pname, relation in session.execute(stmt):
        role = "собственик" if relation == "ownership" else "управител"
        out.setdefault(pid, f"{role} {pname}")
    return out


def _sibling_official_subjects(session, entity_id: Optional[int]) -> dict:
    """Companies co-owned/managed by a person who also controls ``entity_id``.

    Returns ``{company_id: via_label}``. Used to surface *official-tier* signals
    from a sibling SPV on the parent's page (conservative — forum/web never bubble
    up). Label reads e.g. "собственик Елена Иванова → Артекс Златен век ООД".
    """
    out: dict = {}
    if entity_id is None:
        return out
    persons = session.execute(
        select(Entity.id, Entity.name, EntityEdge.relation)
        .join(EntityEdge, Entity.id == EntityEdge.src_entity_id)
        .where(EntityEdge.dst_entity_id == entity_id,
               EntityEdge.relation.in_(("ownership", "management")),
               Entity.kind == "person")
    ).all()
    role_by_person: dict = {}
    for pid, pname, relation in persons:
        role = "собственик" if relation == "ownership" else "управител"
        role_by_person.setdefault(pid, (pname, role))
    if not role_by_person:
        return out
    rows = session.execute(
        select(EntityEdge.src_entity_id, Entity.id, Entity.name)
        .join(Entity, Entity.id == EntityEdge.dst_entity_id)
        .where(EntityEdge.src_entity_id.in_(list(role_by_person)),
               EntityEdge.relation.in_(("ownership", "management")),
               Entity.kind == "company", Entity.id != entity_id)
    ).all()
    for pid, cid, cname in rows:
        pname, role = role_by_person[pid]
        out.setdefault(cid, f"{role} {pname} → {cname}")
    return out


def _signal_dict(s: EntitySignal, via: Optional[str]) -> dict:
    return {
        "tier": s.tier, "source_type": s.source_type, "source_site": s.source_site,
        "match_confidence": s.match_confidence, "subject_kind": s.subject_kind,
        "matched_name": s.matched_name, "title": s.title, "snippet": s.snippet,
        "url": s.url,
        "observed_date": s.observed_date.isoformat() if s.observed_date else None,
        "subject": "self" if via is None else via,  # "self" | "via <role> <name>"
    }


def _signals_for(session, entity_id: Optional[int], include_siblings: bool = False) -> list:
    direct = _signal_subject_ids(session, entity_id)
    sib = _sibling_official_subjects(session, entity_id) if include_siblings else {}
    ids = set(direct) | set(sib)
    if not ids:
        return []
    rows = session.scalars(
        select(EntitySignal).where(EntitySignal.entity_id.in_(list(ids)),
                                   EntitySignal.hidden.is_(False))
    ).all()
    # direct subjects contribute all tiers; sibling companies only official-tier.
    rows = [s for s in rows
            if s.entity_id in direct or (s.entity_id in sib and s.tier == "official")]
    rows.sort(key=lambda s: (_TIER_ORDER.get(s.tier, 9),
                             s.observed_date is None, -(s.observed_date.toordinal()
                             if s.observed_date else 0)))
    return [_signal_dict(s, direct[s.entity_id] if s.entity_id in direct
                         else sib.get(s.entity_id)) for s in rows]


def _signal_counts_for(session, entity_id: Optional[int],
                       include_siblings: bool = False) -> dict:
    counts = {"official": 0, "community": 0, "web": 0}
    direct = _signal_subject_ids(session, entity_id)
    if direct:
        for tier, c in session.execute(
            select(EntitySignal.tier, func.count())
            .where(EntitySignal.entity_id.in_(list(direct)),
                   EntitySignal.hidden.is_(False))
            .group_by(EntitySignal.tier)
        ):
            if tier in counts:
                counts[tier] += c
    if include_siblings:
        sib = _sibling_official_subjects(session, entity_id)
        if sib:
            counts["official"] += session.scalar(
                select(func.count()).select_from(EntitySignal)
                .where(EntitySignal.entity_id.in_(list(sib)),
                       EntitySignal.tier == "official",
                       EntitySignal.hidden.is_(False))
            ) or 0
    return counts


@router.get("/builders/{eik}")
def get_builder(eik: str, session=Depends(get_session),
                user=Depends(current_user_optional)):
    """Full builder profile + its linked new-building projects.

    Owners/managers + research signals are stripped for anonymous viewers (see
    app.auth.scrub) — public callers get name/ЕИК/status/capital/projects only.
    """
    b = session.scalar(select(Builder).where(Builder.eik == eik))
    if b is None:
        raise HTTPException(status_code=404, detail=f"Unknown builder ЕИК: {eik}")
    data = {
        **_builder_summary(b),
        "address": b.address,
        "owners": _incoming_edges(session, b.entity_id, "ownership"),
        "managers": _incoming_edges(session, b.entity_id, "management"),
        "financials": b.financials,
        "last_checked_at": b.last_checked_at.isoformat() if b.last_checked_at else None,
        "projects": [
            {"canonical_key": p.canonical_key, "name": p.name,
             "akt_stage": p.akt_stage, "completion_year": p.completion_year,
             "price_eur_sqm": _f(p.price_eur_sqm)}
            for p in b.projects
        ],
    }
    return scrub(data, user, resource=eik)


# --- Phase 3.5: entity-wide browse (any company/person, not just builders) --


def _resolve_entity(session, key: str) -> Optional[Entity]:
    """Find an entity by ЕИК → person_key → numeric id (in that priority)."""
    e = session.scalar(select(Entity).where(Entity.eik == key))
    if e is not None:
        return e
    e = session.scalar(select(Entity).where(Entity.person_key == key))
    if e is not None:
        return e
    if key.isdigit():
        return session.get(Entity, int(key))
    return None


def _entity_rows(session) -> list:
    """All graph nodes as lightweight dicts, pre-sorted for /entities (builders
    first, then most-connected, then name). The graph only changes at ETL time,
    so this is computed once and cached — type-ahead search then never touches
    the DB. ``_hay`` holds the lowered name/ЕИК/person_key for substring match.
    """
    global _entities_cache
    if _entities_cache is not None:
        return _entities_cache
    deg: dict = {}
    for col in (EntityEdge.src_entity_id, EntityEdge.dst_entity_id):
        for eid, c in session.execute(select(col, func.count()).group_by(col)):
            deg[eid] = deg.get(eid, 0) + c
    rows = [
        {"id": e.id, "eik": e.eik, "person_key": e.person_key,
         "key": e.eik or e.person_key, "slug": e.slug, "kind": e.kind, "name": e.name,
         "is_builder": bool(e.is_builder), "status": e.status,
         "degree": deg.get(e.id, 0),
         "_hay": tuple(v.lower() for v in (e.name, e.eik, e.person_key) if v)}
        for e in session.scalars(select(Entity))
    ]
    rows.sort(key=lambda r: (not r["is_builder"], -r["degree"], r["name"] or ""))
    _entities_cache = rows
    return rows


def _entity_signal_counts(session) -> dict:
    """{entity_id: {"official","community","web"}} for the browse list, matching
    _signal_counts_for's semantics (the entity itself + its owner/manager
    persons; no sibling roll-up). Bulk-computed in two queries and cached —
    the per-row version was an N+1 over the whole table for signed-in users.
    """
    global _entity_signal_counts_cache
    if _entity_signal_counts_cache is not None:
        return _entity_signal_counts_cache
    own: dict = {}
    for eid, tier, c in session.execute(
        select(EntitySignal.entity_id, EntitySignal.tier, func.count())
        .where(EntitySignal.hidden.is_(False))
        .group_by(EntitySignal.entity_id, EntitySignal.tier)
    ):
        row = own.setdefault(eid, {"official": 0, "community": 0, "web": 0})
        if tier in row:
            row[tier] += c
    out = {eid: dict(t) for eid, t in own.items()}
    if own:
        # Roll flagged persons' counts up to every company they own or manage.
        flagged_persons: dict = {}
        for pid, cid in session.execute(
            select(EntityEdge.src_entity_id, EntityEdge.dst_entity_id)
            .join(Entity, Entity.id == EntityEdge.src_entity_id)
            .where(EntityEdge.relation.in_(("ownership", "management")),
                   Entity.kind == "person",
                   EntityEdge.src_entity_id.in_(list(own)))
        ):
            flagged_persons.setdefault(cid, set()).add(pid)
        for cid, pids in flagged_persons.items():
            tgt = out.setdefault(cid, {"official": 0, "community": 0, "web": 0})
            for pid in pids:
                for tier, c in own[pid].items():
                    tgt[tier] += c
    _entity_signal_counts_cache = out
    return out


@router.get("/entities")
def list_entities(
    q: Optional[str] = Query(None, description="name / ЕИК / person_key substring"),
    kind: Optional[str] = Query(None, pattern="^(company|person|builder)$"),
    has_signals: Optional[bool] = Query(None, description="only entities with caution signals"),
    limit: int = Query(50, le=500),
    offset: int = 0,
    session=Depends(get_session),
    user=Depends(current_user_optional),
):
    """Search across ALL graph nodes — companies, builders, and persons.

    This is what makes any developer/owner findable (not just the 134 licensed
    builders). Ordered builders first, then by degree (most-connected), then name.
    Served entirely from the in-process entity cache (see _entity_rows).
    """
    rows = _entity_rows(session)
    if q:
        needle = q.strip().lower()
        if needle:
            rows = [r for r in rows if any(needle in h for h in r["_hay"])]
    if kind == "builder":
        rows = [r for r in rows if r["is_builder"]]
    elif kind in ("company", "person"):
        rows = [r for r in rows if r["kind"] == kind]
    # Research (the ⚠ caution counts) is gated: anonymous viewers get zeros and the
    # has_signals filter is ignored, so the list never leaks which entities are flagged.
    zero = {"official": 0, "community": 0, "web": 0}
    if can_view(user, "research"):
        counts = _entity_signal_counts(session)
        if has_signals:
            rows = [r for r in rows if any(counts.get(r["id"], zero).values())]
    else:
        counts = {}
    page = rows[offset:offset + limit]
    return {
        "total": len(rows), "limit": limit, "offset": offset,
        "items": [
            {**{k: v for k, v in r.items() if k != "_hay"},
             "signal_counts": counts.get(r["id"], zero)}
            for r in page
        ],
    }


@router.get("/entities/{key}/network")
def get_entity_network(
    key: str,
    depth: int = Query(2, ge=1, le=4, description="hops to traverse (Дълбочина)"),
    session=Depends(get_session),
    user=Depends(current_user_optional),
):
    """Ego ownership-network around any entity (company or person)."""
    if not can_view(user, "people"):
        raise HTTPException(status_code=401, detail="Login required to view the network")
    e = _resolve_entity(session, key)
    if e is None:
        raise HTTPException(status_code=404, detail=f"Unknown entity: {key}")
    depths = _ego_depths(session, e.id, depth)
    nodes = session.scalars(select(Entity).where(Entity.id.in_(depths))).all()
    edges = _induced_edges(session, set(depths))
    flagged = _signal_flagged_ids(session, set(depths))
    sig_map = _signals_by_entity(session, set(depths))
    return {
        "center": e.id, "key": key, "depth": depth,
        "nodes": [_node_dict(n, depths.get(n.id), n.id in flagged, sig_map.get(n.id))
                  for n in nodes],
        "edges": [_edge_dict(ed) for ed in edges],
    }


@router.get("/entities/{key}")
def get_entity(key: str, session=Depends(get_session),
               user=Depends(current_user_optional)):
    """Full profile for any entity, with connections in BOTH directions.

    ``owners``/``managers`` = who controls this entity; ``owns``/``manages`` =
    what this entity controls. Builder-only fields (КСБ, projects) appear when
    the entity is a licensed builder. People + research fields are stripped for
    anonymous viewers (see app.auth.scrub).
    """
    e = _resolve_entity(session, key)
    if e is None:
        raise HTTPException(status_code=404, detail=f"Unknown entity: {key}")
    data = {
        "id": e.id, "eik": e.eik, "person_key": e.person_key,
        "key": e.eik or e.person_key, "slug": e.slug, "kind": e.kind, "name": e.name,
        "is_builder": bool(e.is_builder), "status": e.status,
        "legal_form": e.legal_form, "address": e.address,
        "capital_bgn": _f(e.capital_bgn), "founded_year": e.founded_year,
        "owners": _incoming_edges(session, e.id, "ownership"),
        "managers": _incoming_edges(session, e.id, "management"),
        "owns": _outgoing_edges(session, e.id, "ownership"),
        "manages": _outgoing_edges(session, e.id, "management"),
        "projects": [],
        # Court/official records attach ONLY to the company that is a party to them
        # — we do NOT propagate a sibling company's cases across the network (e.g. via
        # a shared manager). A signal on an owner/manager *person* still shows on the
        # companies they control (see _signal_subject_ids); sibling-company rollup is
        # off. (_sibling_official_subjects stays available behind the flag if needed.)
        # Registered against THIS company only (see Entity.has_seizure).
        "has_seizure": bool(e.has_seizure),
        "seizure_count": e.seizure_count or 0,
        "seizure_last_at": e.seizure_last_at.isoformat() if e.seizure_last_at else None,
        "seizure_source_url": e.seizure_source_url,
        "signals": _signals_for(session, e.id, include_siblings=False),
        "signal_counts": _signal_counts_for(session, e.id, include_siblings=False),
    }
    if e.is_builder:
        b = session.scalar(select(Builder).where(Builder.entity_id == e.id))
        if b is not None:
            data.update({
                "legal_form": b.legal_form or data["legal_form"],
                "address": b.address or data["address"],
                "status": b.status or data["status"],
                "ksb_category": b.ksb_category, "ksb_active": b.ksb_active,
                "insolvency_flag": b.insolvency_flag, "tax_debt_bgn": _f(b.tax_debt_bgn),
                "capital_bgn": _f(b.capital_bgn) if b.capital_bgn is not None
                else data["capital_bgn"],
                "projects": [
                    {"canonical_key": p.canonical_key, "name": p.name,
                     "akt_stage": p.akt_stage, "completion_year": p.completion_year,
                     "price_eur_sqm": _f(p.price_eur_sqm)}
                    for p in b.projects
                ],
            })
    return scrub(data, user, resource=e.eik or key)


# --- Phase 3.5: ownership graph (ego-network + global) ----------------------


def _signal_flagged_ids(session, node_ids) -> set:
    """Subset of ``node_ids`` carrying at least one caution signal — directly, or
    via a person who owns/manages them. Mirrors the list view's caution count
    (minus sibling SPVs). Batched into two queries, not one per node."""
    ids = list(node_ids)
    if not ids:
        return set()
    flagged = set(session.scalars(
        select(EntitySignal.entity_id)
        .where(EntitySignal.entity_id.in_(ids), EntitySignal.hidden.is_(False))
        .distinct()
    ).all())
    persons_with_signals = (
        select(EntitySignal.entity_id)
        .join(Entity, Entity.id == EntitySignal.entity_id)
        .where(Entity.kind == "person", EntitySignal.hidden.is_(False)).distinct()
    )
    for _src, dst in session.execute(
        select(EntityEdge.src_entity_id, EntityEdge.dst_entity_id)
        .where(EntityEdge.dst_entity_id.in_(ids),
               EntityEdge.relation.in_(("ownership", "management")),
               EntityEdge.src_entity_id.in_(persons_with_signals))
    ):
        flagged.add(dst)
    return flagged


def _signals_by_entity(session, node_ids) -> dict:
    """Map entity_id -> its own directly-attached, non-hidden signals (minimal
    fields the client needs to classify a legal record). One batched query, so
    the certificate can roll a network-wide record up from the nodes it already
    has. Note: a court act shared across sibling EIKs yields one row per entity —
    dedupe on the client by title if a distinct-cases count is wanted."""
    ids = list(node_ids)
    if not ids:
        return {}
    out: dict = {}
    for s in session.scalars(
        select(EntitySignal).where(EntitySignal.entity_id.in_(ids),
                                   EntitySignal.hidden.is_(False))
    ).all():
        out.setdefault(s.entity_id, []).append({"title": s.title, "snippet": s.snippet})
    return out


def _node_dict(e: Entity, depth: Optional[int] = None, has_signals: bool = False,
               signals: Optional[list] = None) -> dict:
    return {
        "id": e.id, "eik": e.eik, "person_key": e.person_key,
        "key": e.eik or e.person_key, "slug": e.slug, "kind": e.kind, "name": e.name,
        "is_builder": bool(e.is_builder), "depth": depth,
        "has_signals": has_signals, "capital_bgn": _f(e.capital_bgn),
        "signals": signals or [],
    }


def _edge_dict(e: EntityEdge) -> dict:
    # D3-friendly: source/target are node ids; provenance under "via".
    return {
        "source": e.src_entity_id, "target": e.dst_entity_id,
        "relation": e.relation, "share_pct": _f(e.share_pct),
        "role": e.role, "is_current": bool(e.is_current), "via": e.source,
    }


def _induced_edges(session, node_ids):
    """All edges whose both endpoints are within ``node_ids`` (the induced subgraph)."""
    if not node_ids:
        return []
    ids = list(node_ids)
    return session.scalars(
        select(EntityEdge).where(EntityEdge.src_entity_id.in_(ids),
                                 EntityEdge.dst_entity_id.in_(ids))
    ).all()


def _ego_depths(session, center_id: int, depth: int) -> dict:
    """BFS over (undirected) edges from ``center_id`` -> {entity_id: hop distance}.

    Only direct edges are stored; this expands them to a depth-bounded node set.
    Portable (Python BFS, not a DB-specific recursive CTE) and fine at our scale.
    """
    depths = {center_id: 0}
    frontier = {center_id}
    for d in range(1, depth + 1):
        if not frontier:
            break
        rows = session.execute(
            select(EntityEdge.src_entity_id, EntityEdge.dst_entity_id).where(
                or_(EntityEdge.src_entity_id.in_(frontier),
                    EntityEdge.dst_entity_id.in_(frontier))
            )
        ).all()
        nxt = set()
        for s_id, t_id in rows:
            for nid in (s_id, t_id):
                if nid not in depths:
                    depths[nid] = d
                    nxt.add(nid)
        frontier = nxt
    return depths


@router.get("/builders/{eik}/network")
def get_builder_network(
    eik: str,
    depth: int = Query(2, ge=1, le=4, description="hops to traverse (Дълбочина)"),
    session=Depends(get_session),
    user=Depends(current_user_optional),
):
    """Ego ownership-network around one builder, expanded to ``depth`` hops."""
    if not can_view(user, "people"):
        raise HTTPException(status_code=401, detail="Login required to view the network")
    b = session.scalar(select(Builder).where(Builder.eik == eik))
    if b is None or b.entity_id is None:
        raise HTTPException(status_code=404, detail=f"Unknown builder ЕИК: {eik}")
    depths = _ego_depths(session, b.entity_id, depth)
    nodes = session.scalars(select(Entity).where(Entity.id.in_(depths))).all()
    edges = _induced_edges(session, set(depths))
    flagged = _signal_flagged_ids(session, set(depths))
    return {
        "center": b.entity_id, "eik": eik, "depth": depth,
        "nodes": [_node_dict(n, depths.get(n.id), n.id in flagged) for n in nodes],
        "edges": [_edge_dict(e) for e in edges],
    }


@router.get("/graph")
def get_graph(
    limit: int = Query(500, ge=1, le=2000, description="max nodes (builders first)"),
    session=Depends(get_session),
    user=Depends(current_user_optional),
):
    """Bounded global network — all builders plus the entities around them.

    Cached in memory per ``limit`` (see ``clear_caches``). ~250ms of DB work at
    limit=2000 — the entity browse page refetches this on every visit, and the
    payload is identical for every signed-in viewer (no per-user scrubbing here),
    so one shared entry is safe. The gate below stays OUTSIDE the cache: anonymous
    callers must still get 401, never a cached body.
    """
    if not can_view(user, "people"):
        raise HTTPException(status_code=401, detail="Login required to view the graph")
    if limit in _graph_cache:
        return _graph_cache[limit]
    nodes = session.scalars(
        select(Entity).order_by(Entity.is_builder.desc(), Entity.id).limit(limit)
    ).all()
    ids = {n.id for n in nodes}
    edges = _induced_edges(session, ids)
    flagged = _signal_flagged_ids(session, ids)
    payload = {
        "nodes": [_node_dict(n, has_signals=n.id in flagged) for n in nodes],
        "edges": [_edge_dict(e) for e in edges],
        "truncated": len(nodes) >= limit,
    }
    while len(_graph_cache) >= _GRAPH_CACHE_MAX:
        _graph_cache.pop(next(iter(_graph_cache)))  # dicts keep insertion order
    _graph_cache[limit] = payload
    return payload


def _project_dict(p: NewBuilding) -> dict:
    return {
        "canonical_key": p.canonical_key, "name": p.name,
        "developer_name": p.developer_name,
        "developer_eik": p.developer.eik if p.developer else None,
        "akt_stage": p.akt_stage, "completion_year": p.completion_year,
        "floors": p.floors, "materials": p.materials,
        "price_eur_sqm": _f(p.price_eur_sqm),
        "area_min_sqm": _f(p.area_min_sqm), "area_max_sqm": _f(p.area_max_sqm),
        "sources": [{"site": s.site, "source_name": s.source_name, "url": s.url,
                     "price_eur_sqm": _f(s.price_eur_sqm)} for s in p.sources],
    }


@router.get("/neighbourhoods/{slug}/projects")
def get_neighbourhood_projects(slug: str, city: Optional[str] = None,
                               session=Depends(get_session)):
    """Canonical new-building projects in one neighbourhood."""
    n = _resolve_neighbourhood(session, slug, city)
    if n is None:
        raise HTTPException(status_code=404, detail=f"Unknown neighbourhood: {slug}")
    rows = session.scalars(
        select(NewBuilding).where(NewBuilding.neighbourhood_id == n.id)
    ).all()
    return [_project_dict(p) for p in rows]


@router.get("/cities/{slug}/projects")
def get_city_projects(slug: str, session=Depends(get_session)):
    """All canonical new-building projects in one city."""
    c = session.scalar(select(City).where(City.slug == slug))
    if c is None:
        raise HTTPException(status_code=404, detail=f"Unknown city: {slug}")
    rows = session.scalars(select(NewBuilding).where(NewBuilding.city_id == c.id)).all()
    return [_project_dict(p) for p in rows]


@router.get("/reference/gold")
def get_gold(session=Depends(get_session)):
    """Monthly gold price, EUR per gram, ascending by date."""
    rows = session.scalars(select(GoldPrice).order_by(GoldPrice.period_date)).all()
    return [{"period_date": r.period_date.isoformat(),
             "price_eur_per_gram": _f(r.price_eur_per_gram)} for r in rows]


@router.get("/reference/min-wage")
def get_min_wage(session=Depends(get_session)):
    """Bulgaria minimum monthly wage by year, ascending."""
    rows = session.scalars(select(MinWage).order_by(MinWage.year)).all()
    return [{"year": r.year, "amount_eur": _f(r.amount_eur),
             "amount_bgn": _f(r.amount_bgn)} for r in rows]


# --- "Order a research" lead capture -----------------------------------------
# Public (no login gate): when a visitor's search returns nothing, they can ask us
# to research a company. A server-verified math CAPTCHA + honeypot keep bots out;
# the schema whitelist-sanitises every field before it reaches the ORM.


@router.get("/research-requests/challenge")
def research_challenge():
    """A fresh signed math challenge for the order form: ``{question, exp, sig}``."""
    return captcha.make_challenge()


@router.post("/research-requests", response_model=ResearchRequestRead, status_code=201)
def create_research_request(
    payload: ResearchRequestCreate,
    session=Depends(get_session),
    user=Depends(current_user_optional),
):
    """Store a research request. CAPTCHA is verified before anything touches the DB."""
    captcha.verify(payload.captcha_answer, payload.captcha_exp, payload.captcha_sig)
    data = payload.model_dump(
        exclude={"captcha_answer", "captcha_exp", "captcha_sig", "website"}
    )
    # Pay-to-expedite: run this single company ASAP at the per-company court price.
    # No EIK -> name-only (fuzzier) pricing. Price is computed here, never trusted from
    # the client. Plain (queued) leads keep order_type='lead' and no price.
    if data.pop("expedited", False):
        search_type = data.get("search_type") or ("eik" if data.get("company_eik") else "eik_name")
        data.update(
            order_type="court_research", scope="company", search_type=search_type,
            entity_count=1, price_eur=pricing.quote_single(search_type), expedited=True,
        )
    else:
        data.pop("search_type", None)
    rr = ResearchRequest(**data, user_id=user.id if user else None)
    session.add(rr)
    session.commit()
    session.refresh(rr)
    return rr


@router.post("/research-requests/court-order",
             response_model=CourtResearchOrderRead, status_code=201)
def create_court_order(
    payload: CourtResearchOrderCreate,
    session=Depends(get_session),
    user=Depends(current_user),
):
    """Order a court check on one company or its whole network (login required).

    The price is recomputed here from the live ego-network so the client can't
    tamper with it; only companies with an EIK are billable (persons have none).
    Lands in the shared ``research_request`` inbox as ``order_type='court_research'``.
    """
    e = _resolve_entity(session, payload.key)
    if e is None:
        raise HTTPException(status_code=404, detail=f"Unknown entity: {payload.key}")

    if payload.scope == "network":
        depths = _ego_depths(session, e.id, payload.depth)
        nodes = session.scalars(select(Entity).where(Entity.id.in_(depths))).all()
        count = sum(1 for n in nodes if n.kind == "company" and n.eik)
        price = pricing.quote_network(count, payload.search_type)
    else:
        count = 1 if (e.kind == "company" and e.eik) else 0
        price = pricing.quote_single(payload.search_type) if count else 0.0

    rr = ResearchRequest(
        order_type="court_research", company_name=e.name, company_eik=e.eik,
        scope=payload.scope, search_type=payload.search_type,
        network_depth=payload.depth if payload.scope == "network" else None,
        entity_count=count, price_eur=price, details=payload.details,
        requester_email=user.email, user_id=user.id, status="new",
    )
    session.add(rr)
    session.commit()
    session.refresh(rr)
    return rr


# --- Admin (superuser-only read views) ---------------------------------------
# Plain read endpoints behind ``current_superuser`` (401 anonymous / 403 non-admin).


@router.get("/admin/research-requests", response_model=list[AdminResearchRequestRead])
def admin_research_requests(
    limit: int = Query(500, ge=1, le=2000),
    session=Depends(get_session),
    _admin=Depends(current_superuser),
):
    """Every research request (leads + court orders + expedite), newest first.

    Each row carries two derived coverage flags the inbox renders as checkboxes:
    whether we hold the company (``in_db``) and when we last ran a court search
    for its ЕИК (``court_checked_at``). The court flag reads ``court_check``, the
    log of searches performed — **not** signal presence, because a search that
    finds no acts writes no signal and would otherwise look like "never checked".
    """
    requests = session.scalars(
        select(ResearchRequest).order_by(ResearchRequest.created_at.desc()).limit(limit)
    ).all()
    flags = coverage_flags(session, requests)
    out = []
    for r in requests:
        row = AdminResearchRequestRead.model_validate(r)
        for key, value in flags[r.id].items():
            setattr(row, key, value)
        out.append(row)
    return out


@router.get("/admin/users", response_model=list[AdminUserRead])
def admin_users(
    session=Depends(get_session),
    _admin=Depends(current_superuser),
):
    """All registered users."""
    # User.oauth_accounts is a joined-eager collection -> .unique() is required.
    return session.scalars(select(User).order_by(User.id)).unique().all()
