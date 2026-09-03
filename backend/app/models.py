"""SQLAlchemy models — MVP subset of the schema in HANDOVER.md §6.

Included: city, neighbourhood, price_snapshot, metro_station, neighbourhood_metro.
Deferred (not MVP): neighbourhood_adjacency (needs manual curation).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from fastapi_users_db_sqlalchemy import (SQLAlchemyBaseOAuthAccountTable,
                                         SQLAlchemyBaseUserTable)
from sqlalchemy import (JSON, BigInteger, Boolean, ForeignKey, Integer, Numeric, String,
                        Text, UniqueConstraint, false, func)
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from app.db import Base


class City(Base):
    __tablename__ = "city"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(String, unique=True)

    neighbourhoods: Mapped[List["Neighbourhood"]] = relationship(back_populates="city")


class Neighbourhood(Base):
    __tablename__ = "neighbourhood"
    # Slugs are unique *within* a city, not globally — imot.bg reuses slugs across
    # cities (every city has a "tsentar", Varna & Burgas both have "lazur", …).
    __table_args__ = (
        UniqueConstraint("city_id", "slug", name="uq_neighbourhood_city_slug"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("city.id"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(String)
    district: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    lat: Mapped[Optional[float]] = mapped_column(Numeric(9, 7), nullable=True)
    lon: Mapped[Optional[float]] = mapped_column(Numeric(9, 7), nullable=True)
    coord_source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    city: Mapped["City"] = relationship(back_populates="neighbourhoods")
    prices: Mapped[List["PriceSnapshot"]] = relationship(back_populates="neighbourhood")


class PriceSnapshot(Base):
    __tablename__ = "price_snapshot"

    id: Mapped[int] = mapped_column(primary_key=True)
    neighbourhood_id: Mapped[int] = mapped_column(ForeignKey("neighbourhood.id"))
    source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    property_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    transaction_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 'sale' | 'rent'
    price_eur: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    price_eur_sqm: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    overall_avg_eur_sqm: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    period_date: Mapped[Optional[date]] = mapped_column(nullable=True)
    scraped_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    neighbourhood: Mapped["Neighbourhood"] = relationship(back_populates="prices")


class MetroStation(Base):
    __tablename__ = "metro_station"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    line: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    lat: Mapped[Optional[float]] = mapped_column(Numeric(9, 7), nullable=True)
    lon: Mapped[Optional[float]] = mapped_column(Numeric(9, 7), nullable=True)
    sequence: Mapped[Optional[int]] = mapped_column(nullable=True)


class NeighbourhoodMetro(Base):
    __tablename__ = "neighbourhood_metro"

    neighbourhood_id: Mapped[int] = mapped_column(
        ForeignKey("neighbourhood.id"), primary_key=True
    )
    station_id: Mapped[int] = mapped_column(
        ForeignKey("metro_station.id"), primary_key=True
    )
    distance_m: Mapped[Optional[int]] = mapped_column(nullable=True)


class GoldPrice(Base):
    """Monthly gold price in EUR per gram (reference series for 'cost in gold')."""

    __tablename__ = "gold_price"

    id: Mapped[int] = mapped_column(primary_key=True)
    period_date: Mapped[date] = mapped_column(nullable=False, unique=True)
    price_eur_per_gram: Mapped[float] = mapped_column(Numeric, nullable=False)
    source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class MinWage(Base):
    """Bulgaria minimum monthly wage by year (reference series for affordability)."""

    __tablename__ = "min_wage"

    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column(nullable=False, unique=True)
    amount_bgn: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    amount_eur: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# --- Air quality: station registry + annual averages + neighbourhood mapping ---


class AirQualityStation(Base):
    """An air quality monitoring station (official government or citizen sensor)."""

    __tablename__ = "air_quality_station"

    id: Mapped[int] = mapped_column(primary_key=True)
    city_id: Mapped[Optional[int]] = mapped_column(ForeignKey("city.id"), nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)  # 'official' | 'citizen'
    lat: Mapped[Optional[float]] = mapped_column(Numeric(9, 7), nullable=True)
    lon: Mapped[Optional[float]] = mapped_column(Numeric(9, 7), nullable=True)
    external_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    snapshots: Mapped[List["AirQualitySnapshot"]] = relationship(
        back_populates="station", cascade="all, delete-orphan"
    )


class AirQualitySnapshot(Base):
    """Annual average air quality readings for one station."""

    __tablename__ = "air_quality_snapshot"
    __table_args__ = (
        UniqueConstraint("station_id", "year", name="uq_aq_station_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("air_quality_station.id"))
    year: Mapped[int] = mapped_column(nullable=False)
    pm25_annual_avg: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    aqi_annual_avg: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)

    station: Mapped["AirQualityStation"] = relationship(back_populates="snapshots")


class NeighbourhoodAirStation(Base):
    """Maps each neighbourhood to its nearest air quality station (pre-computed).

    NOTE (2026-06-17): superseded by :class:`NeighbourhoodAir`. The historical
    air layer now stores per-neighbourhood seasonal *averages* (winter/summer)
    rather than mapping to a single nearest sensor. This table plus
    ``air_quality_station`` / ``air_quality_snapshot`` are retained but unused;
    safe to drop in a later cleanup migration.
    """

    __tablename__ = "neighbourhood_air_station"

    neighbourhood_id: Mapped[int] = mapped_column(
        ForeignKey("neighbourhood.id"), primary_key=True
    )
    station_id: Mapped[int] = mapped_column(
        ForeignKey("air_quality_station.id"), primary_key=True
    )
    distance_m: Mapped[Optional[int]] = mapped_column(nullable=True)


class NeighbourhoodAir(Base):
    """Seasonal air quality per neighbourhood — the viz-ready aggregate.

    One row per (neighbourhood, year, season). ``season`` is ``'winter'`` (January)
    or ``'summer'`` (July) — Sofia's air is ~3–5× worse in the heating season, so a
    single annual mean would hide the story. Each value is the average of *all*
    citizen sensors assigned to the neighbourhood that season (averaging many cheap
    SDS011 sensors cancels their noise). ``sensor_count`` records how many fed the
    average (a confidence hint). Tiny by construction: ~62 × years × 2 rows.
    """

    __tablename__ = "neighbourhood_air"
    __table_args__ = (
        UniqueConstraint("neighbourhood_id", "year", "season", name="uq_nbhd_air"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    neighbourhood_id: Mapped[int] = mapped_column(
        ForeignKey("neighbourhood.id"), index=True
    )
    year: Mapped[int] = mapped_column(nullable=False)
    season: Mapped[str] = mapped_column(String, nullable=False)  # 'winter' | 'summer'
    pm25_avg: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    aqi_avg: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    sensor_count: Mapped[Optional[int]] = mapped_column(nullable=True)


# --- Phase 3: builders (primary), new-building projects, crawl telemetry -----


class Builder(Base):
    """A construction company / property developer, canonicalised on ЕИК.

    Identity + ownership + size come from the BRRA open data; trust signals
    (КСБ licence, insolvency, tax debt) are merged in by the normalizer.
    """

    __tablename__ = "builder"

    id: Mapped[int] = mapped_column(primary_key=True)
    eik: Mapped[str] = mapped_column(String, unique=True, index=True)  # 9-digit company id
    name: Mapped[str] = mapped_column(Text, nullable=False)
    legal_form: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    hq_city_id: Mapped[Optional[int]] = mapped_column(ForeignKey("city.id"), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    capital_bgn: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # active/liquidation/insolvency
    financials: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    ksb_category: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ksb_active: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    insolvency_flag: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    tax_debt_bgn: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    # Phase 3.5: the builder's node in the ownership graph (owners/managers live as edges).
    entity_id: Mapped[Optional[int]] = mapped_column(ForeignKey("entity.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    entity: Mapped[Optional["Entity"]] = relationship(back_populates="builder")
    projects: Mapped[List["NewBuilding"]] = relationship(back_populates="developer")


# --- Phase 3.5: ownership graph (entities + directed edges) ------------------


class Entity(Base):
    """A node in the ownership graph — a company OR a person.

    A *builder* is an :class:`Entity` of kind ``company`` with ``is_builder``
    set; its rich profile lives in the :class:`Builder` extension. Companies are
    keyed by ``eik``; persons (no national id) by ``person_key``.
    """

    __tablename__ = "entity"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)  # 'company' | 'person'
    eik: Mapped[Optional[str]] = mapped_column(String, unique=True, index=True, nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_normalized: Mapped[Optional[str]] = mapped_column(Text, index=True, nullable=True)
    # Cosmetic, SEO-friendly URL slug derived from `name` (see app.slugs.slugify).
    # Not unique and not used for lookup — eik/person_key/id remain the keys.
    slug: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    person_key: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)
    is_builder: Mapped[bool] = mapped_column(Boolean, default=False)
    legal_form: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    capital_bgn: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    # Year of incorporation (Papagal "Дата на регистрация"); year-granularity only.
    founded_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # --- запор върху дружествен дял (attachment on a partner's share) --------
    # A creditor enforcing against a partner personally can attach their share in
    # the company. It is registered in the Търговски регистър and never appears in
    # legalacts.justice.bg, because enforcement runs before a частен съдебен
    # изпълнител, not a court — so a company under active enforcement looks clean
    # in the court portal. Flagged on the company it is registered against ONLY;
    # deliberately NOT propagated to siblings, which the register says nothing about.
    has_seizure: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    seizure_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    seizure_last_at: Mapped[Optional[date]] = mapped_column(nullable=True)
    seizure_source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    first_seen: Mapped[Optional[date]] = mapped_column(nullable=True)
    last_seen: Mapped[Optional[date]] = mapped_column(nullable=True)
    source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    builder: Mapped[Optional["Builder"]] = relationship(back_populates="entity")
    out_edges: Mapped[List["EntityEdge"]] = relationship(
        back_populates="src", foreign_keys="EntityEdge.src_entity_id",
        cascade="all, delete-orphan",
    )
    in_edges: Mapped[List["EntityEdge"]] = relationship(
        back_populates="dst", foreign_keys="EntityEdge.dst_entity_id",
        cascade="all, delete-orphan",
    )
    signals: Mapped[List["EntitySignal"]] = relationship(
        back_populates="entity", cascade="all, delete-orphan",
    )


class EntityEdge(Base):
    """A directed connection between two entities.

    ``ownership`` → src owns dst (``share_pct`` = дял); ``management`` → src
    (a person) manages dst (``role``). Only **direct** edges are stored;
    indirect links are graph paths computed by a depth-bounded traversal.
    """

    __tablename__ = "entity_edge"
    __table_args__ = (
        UniqueConstraint(
            "src_entity_id", "dst_entity_id", "relation", "valid_from",
            name="uq_entity_edge",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    src_entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"), index=True)
    dst_entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"), index=True)
    relation: Mapped[str] = mapped_column(String, nullable=False)  # 'ownership' | 'management'
    share_pct: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)  # ownership only
    role: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # e.g. управител
    valid_from: Mapped[Optional[date]] = mapped_column(nullable=True)
    valid_to: Mapped[Optional[date]] = mapped_column(nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    src: Mapped["Entity"] = relationship(back_populates="out_edges", foreign_keys=[src_entity_id])
    dst: Mapped["Entity"] = relationship(back_populates="in_edges", foreign_keys=[dst_entity_id])


class EntitySignal(Base):
    """A single piece of public evidence about a company OR a person.

    This is the "double-check this developer" feed: insolvency cases, forum
    complaints, web mentions. It is an **evidence aggregator, not a verdict** —
    every row links to its public source with a date, carries a confidence
    (how sure are we this is the same entity), and is never our own accusation.

    ``entity_id`` is the graph node the evidence is *about* (a company or a
    person); it is nullable so a name-only hit can be stored before/without an
    entity match. A builder's caution badge aggregates signals about its own
    entity **plus** signals about its owners/managers (propagated via the graph).

    Idempotency: upsert on ``url`` (one canonical source link = one signal).
    """

    __tablename__ = "entity_signal"
    __table_args__ = (
        UniqueConstraint("url", "matched_name", name="uq_entity_signal_url_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("entity.id"), index=True, nullable=True
    )
    subject_kind: Mapped[str] = mapped_column(String, nullable=False)  # 'company' | 'person'
    matched_name: Mapped[str] = mapped_column(Text, nullable=False)
    matched_eik: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)
    matched_person_key: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)
    source_type: Mapped[str] = mapped_column(String, nullable=False)  # registry|forum|web
    tier: Mapped[str] = mapped_column(String, nullable=False)         # official|community|web
    match_confidence: Mapped[str] = mapped_column(String, nullable=False)  # eik|fuzzy_high|fuzzy_low
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(Text, index=True)
    source_site: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    observed_date: Mapped[Optional[date]] = mapped_column(nullable=True)
    scraped_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    entity: Mapped[Optional["Entity"]] = relationship(back_populates="signals")


class NewBuilding(Base):
    """A canonical new-construction project (deduped across listing sites)."""

    __tablename__ = "new_building"

    id: Mapped[int] = mapped_column(primary_key=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("city.id"))
    neighbourhood_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("neighbourhood.id"), nullable=True
    )
    canonical_key: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    developer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("builder.id"), nullable=True)
    developer_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # pre-ЕИК-resolution
    akt_stage: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 'Акт 14'|'Акт 15'|'Акт 16'
    completion_year: Mapped[Optional[int]] = mapped_column(nullable=True)
    floors: Mapped[Optional[int]] = mapped_column(nullable=True)
    materials: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    price_eur_sqm: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    area_min_sqm: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    area_max_sqm: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    first_seen: Mapped[Optional[date]] = mapped_column(nullable=True)
    last_seen: Mapped[Optional[date]] = mapped_column(nullable=True)

    developer: Mapped[Optional["Builder"]] = relationship(back_populates="projects")
    sources: Mapped[List["NewBuildingSource"]] = relationship(
        back_populates="new_building", cascade="all, delete-orphan"
    )


class NewBuildingSource(Base):
    """One listing of a project on one site — the cross-site dedup audit trail.

    The same project may appear under different names on different sites
    ("Luxury Skyscraper" vs "Top Skyscraper"); each site listing is kept here,
    all pointing at the one canonical :class:`NewBuilding`.
    """

    __tablename__ = "new_building_source"

    id: Mapped[int] = mapped_column(primary_key=True)
    new_building_id: Mapped[int] = mapped_column(ForeignKey("new_building.id"))
    site: Mapped[str] = mapped_column(String, nullable=False)
    source_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # the site's own name
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    price_eur_sqm: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    scraped_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    new_building: Mapped["NewBuilding"] = relationship(back_populates="sources")


class CrawlRun(Base):
    """Telemetry for a single scraper run — powers the GET /api/stats counter."""

    __tablename__ = "crawl_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    domain: Mapped[str] = mapped_column(String, nullable=False)  # builders | new_buildings
    site: Mapped[str] = mapped_column(String, nullable=False)
    scope: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # city slug or country
    city_id: Mapped[Optional[int]] = mapped_column(ForeignKey("city.id"), nullable=True)
    pages_fetched: Mapped[int] = mapped_column(default=0)
    bytes_downloaded: Mapped[int] = mapped_column(BigInteger, default=0)
    records_parsed: Mapped[int] = mapped_column(default=0)
    records_emitted: Mapped[int] = mapped_column(default=0)
    errors: Mapped[int] = mapped_column(default=0)
    duration_s: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)


# --- Auth: app users (login gates the owner/research data) -------------------
# Identity + login is handled by the fastapi-users library; these two tables are
# its required schema. ``tier`` is our own forward-compatible seam (see
# app/auth.py can_view): today it just means "logged-in member", later it carries
# membership levels / per-builder report entitlements.


class OAuthAccount(SQLAlchemyBaseOAuthAccountTable[int], Base):
    """A linked third-party login (Google) for a :class:`User` — managed by fastapi-users."""

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    @declared_attr
    def user_id(cls) -> Mapped[int]:
        return mapped_column(
            Integer, ForeignKey("user.id", ondelete="cascade"), nullable=False
        )


class User(SQLAlchemyBaseUserTable[int], Base):
    """An application user. Base columns (email, hashed_password, is_active, …) come
    from fastapi-users; ``name`` and ``tier`` are ours."""

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tier: Mapped[str] = mapped_column(
        Text, nullable=False, default="member", server_default="member"
    )
    oauth_accounts: Mapped[List["OAuthAccount"]] = relationship(
        "OAuthAccount", lazy="joined", cascade="all, delete-orphan"
    )


# --- Lead capture: "Order a research" requests -------------------------------
# When a visitor searches the builder/company graph and finds nothing, they can
# ask us to research a company. This is the captured request — stored verbatim
# (already whitelist-sanitised at the schema layer) for manual follow-up. No
# notification/admin workflow yet; ``status`` is the seam for a future triage view.


class ResearchRequest(Base):
    """A visitor-submitted request to research a company we don't yet cover."""

    __tablename__ = "research_request"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_name: Mapped[str] = mapped_column(Text, nullable=False)
    company_eik: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    owner: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requester_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requester_email: Mapped[str] = mapped_column(String, nullable=False)
    search_query: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user.id"), index=True, nullable=True
    )
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="new", server_default="new"
    )
    # Court / deep-research orders share this inbox with plain leads. ``order_type``
    # discriminates them; the rest carry the quote we computed (see app.pricing).
    order_type: Mapped[str] = mapped_column(
        String, nullable=False, default="lead", server_default="lead"
    )  # 'lead' | 'court_research'
    scope: Mapped[Optional[str]] = mapped_column(String, nullable=True)        # 'company' | 'network'
    search_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # 'eik' | 'eik_name'
    network_depth: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    entity_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    price_eur: Mapped[Optional[float]] = mapped_column(Numeric, nullable=True)
    expedited: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    # Delivery: what we sent back, and when. Written by the sync API when a
    # findings bundle is applied (see app/sync/router.py).
    report_md: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


# --- Court-check log ---------------------------------------------------------
# A court search that finds nothing writes no ``entity_signal`` row, so "has
# signals" can never answer "did we check this company?". This table records the
# *search event* itself — including the zero-result ones — which is what the
# admin inbox's "court checked" box reads. One row per search, so repeat checks
# build a history and ``max(checked_at)`` is the last-checked date.


class CourtCheck(Base):
    """One legalacts.justice.bg search we actually ran, result irrelevant."""

    __tablename__ = "court_check"

    id: Mapped[int] = mapped_column(primary_key=True)
    eik: Mapped[str] = mapped_column(String, index=True, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # How we searched: 'eik' (ЕИК digits) or 'name'. The playbook recommends the
    # union of both; recording it keeps an ЕИК-only pass honest about its scope.
    method: Mapped[str] = mapped_column(
        String, nullable=False, default="eik", server_default="eik"
    )
    acts_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_site: Mapped[str] = mapped_column(
        String, nullable=False, default="legalacts.justice.bg",
        server_default="legalacts.justice.bg",
    )
    checked_at: Mapped[datetime] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


# --- Sync audit log ----------------------------------------------------------
# Every bundle pushed from the MacBook lands here, dry-runs included, so there is
# a record of what was applied to production and when. ``summary`` is the diff
# report the endpoint returned (counts per table + the first N field changes).


class SyncLog(Base):
    """One push from the research machine to production."""

    __tablename__ = "sync_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("research_request.id"), index=True, nullable=True
    )
    action: Mapped[str] = mapped_column(String, nullable=False)  # 'findings' | 'bundle'
    dry_run: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    summary: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
