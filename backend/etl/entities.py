"""Phase-3.5 ownership-graph helpers — entities + directed edges.

A *builder* is an :class:`Entity` of kind ``company`` flagged ``is_builder``;
``builder.entity_id`` links the rich profile to its graph node. These helpers
keep that backing entity in sync and upsert edges idempotently, so the ETL is
safe to re-run on a schedule.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional, Tuple

from sqlalchemy import select

from app.entities import (  # noqa: F401 — re-exported for existing ETL callers
    BGN_PER_EUR,
    entity_for_builder,
    entity_for_company,
    entity_for_person,
    upsert_edge,
)
from app.models import Builder, Entity, EntityEdge


def backfill_builder_entities(session) -> int:
    """Ensure every :class:`Builder` has a backing entity. Returns count created.

    Used by the 3.5 migration to lift the existing builder rows into the graph,
    and safe to re-run (already-linked builders are skipped).
    """
    created = 0
    for builder in session.scalars(select(Builder)):
        before = builder.entity_id
        entity = entity_for_builder(session, builder)
        if before is None and entity is not None:
            created += 1
    session.flush()
    return created


def find_stub_company_eiks(session) -> list[str]:
    """ЕИКs of company entities only ever seen as an edge target, never scraped directly.

    Depth-2/3 expansion (``_load_person_participations``, a related-company
    mention) creates a node from a listing page that has no capital/legal_form —
    only a company's own Papagal page has those. ``legal_form`` is the signal:
    it's set only by a direct scrape, so its absence means "stub."
    """
    rows = session.scalars(
        select(Entity.eik).where(
            Entity.kind == "company",
            Entity.eik.is_not(None),
            Entity.legal_form.is_(None),
        )
    )
    return [eik for eik in rows if eik]


def backfill_stub_companies(session) -> dict:
    """Directly scrape every stub company and reload it, so none stay permanently empty.

    This is the fix for the gap where depth-2/3 expansion left ~84% of the graph
    as name+ЕИК-only nodes: every ETL run now closes that gap itself instead of
    requiring a manual backfill pass.
    """
    import sys
    from pathlib import Path as _Path

    sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
    from crawlers.scraper_kit.sites.papagal import PapagalScraper

    eiks = find_stub_company_eiks(session)
    if not eiks:
        return {"stubs_found": 0, "scraped": 0}

    out_path = PapagalScraper("bg", eiks=eiks).run()
    report = OwnershipReport()
    with out_path.open(encoding="utf-8") as fh:
        import json
        load_ownership(session, (json.loads(line) for line in fh if line.strip()), report)
    session.flush()
    return {
        "stubs_found": len(eiks),
        "scraped": report.companies_created + report.edges_upserted,
        "report": report,
    }


def derive_insolvency_flags(session) -> int:
    """Set ``Builder.insolvency_flag`` from the backing entity's Papagal status.

    Uses the status Papagal already stores on the company entity (несъстоятелност /
    ликвидация / заличен). Only flips builders whose value would change; returns the
    number updated. Idempotent.
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from crawlers.scraper_kit.sites.papagal import insolvency_from_status

    updated = 0
    rows = session.execute(
        select(Builder, Entity).join(Entity, Entity.id == Builder.entity_id)
    ).all()
    for builder, entity in rows:
        flag = insolvency_from_status(entity.status)
        # Set explicitly (incl. None -> False) so the flag is deterministic.
        if builder.insolvency_flag != flag:
            builder.insolvency_flag = flag
            updated += 1
    session.flush()
    return updated

# --- ownership ingest (Papagal raw edge records -> graph) -------------------


@dataclass
class OwnershipReport:
    companies_created: int = 0
    persons_created: int = 0
    edges_upserted: int = 0

def load_ownership(session, records: Iterable[dict], report: OwnershipReport) -> None:
    """Ingest raw per-company edge records (Papagal) into entities + directed edges.

    Idempotent: companies upsert on ЕИК, persons on ``person_key``, edges on their
    natural key. ``direction`` ``"in"`` means related → company (an owner/manager);
    ``"out"`` means company → related (e.g. a subsidiary). Provenance flows from the
    record's ``source`` onto every node and edge.
    """
    for rec in records:
        if rec.get("kind") == "person_participations":
            _load_person_participations(session, rec, report)
            continue
        eik = rec.get("eik")
        if not eik:
            continue
        src_name = rec.get("source")
        company, created = entity_for_company(
            session, eik, name=rec.get("name"), legal_form=rec.get("legal_form"),
            status=rec.get("status"), address=rec.get("address"),
            capital_eur=rec.get("capital_eur"), founded_year=rec.get("founded_year"),
            source=src_name,
        )
        report.companies_created += int(created)

        for r in rec.get("related", []):
            if r.get("kind") == "person":
                other, made = entity_for_person(
                    session, r.get("name") or "", r.get("person_key"), source=src_name,
                )
                report.persons_created += int(made)
            elif r.get("eik"):
                other, made = entity_for_company(
                    session, r["eik"], name=r.get("name"), source=src_name,
                )
                report.companies_created += int(made)
            else:
                continue

            if r.get("direction") == "out":
                src_id, dst_id = company.id, other.id
            else:  # "in" (default): the related entity owns/manages this company
                src_id, dst_id = other.id, company.id

            upsert_edge(
                session, src_id, dst_id, r.get("relation") or "ownership",
                share_pct=r.get("share_pct"), role=r.get("role"),
                is_current=r.get("is_current", True), source=src_name,
            )
            report.edges_upserted += 1


def _load_person_participations(session, rec: dict, report: OwnershipReport) -> None:
    """Depth-2: a person's page lists every company they own/manage -> edges out."""
    person_key = rec.get("person_key")
    src_name = rec.get("source")
    person, made = entity_for_person(session, rec.get("name") or "", person_key, source=src_name)
    report.persons_created += int(made)

    for c in rec.get("companies", []):
        eik = c.get("eik")
        if not eik:
            continue
        company, created = entity_for_company(
            session, eik, name=c.get("name"), source=src_name,
        )
        report.companies_created += int(created)
        upsert_edge(
            session, person.id, company.id, c.get("relation") or "ownership",
            share_pct=c.get("share_pct"), role=c.get("role"),
            is_current=c.get("is_current", True), source=src_name,
        )
        report.edges_upserted += 1
