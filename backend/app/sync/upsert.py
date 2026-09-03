"""Apply a findings bundle to the database, with a field-level diff.

Contract:

* **Natural keys only.** Companies key on ЕИК, persons on ``person_key``, edges
  on ``(src, dst, relation, valid_from)``, signals on ``(url, matched_name)``,
  court checks on ``(eik, source_site, checked_at)``. Local ids never appear.
* **Enrich, don't erase.** An omitted or null field never overwrites a non-null
  production value — that is what makes re-pushing a partial bundle safe.
* **Flush, never commit.** The caller owns the transaction; a dry run is the
  same code path followed by a rollback.
* **All or nothing.** An unresolvable reference raises :class:`BundleError` and
  the caller rolls back — a half-applied bundle is worse than none.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_, select

from app.entities import (entity_for_builder, entity_for_company, entity_for_person,
                          upsert_edge)
from app.models import Builder, CourtCheck, Entity, EntityEdge, EntitySignal
from app.sync.schemas import Bundle, EntityRef

MAX_CHANGES = 200

# ``created_at`` is server-defaulted and always differs; it is noise in a diff.
_IGNORED_COLS = {"created_at"}


class BundleError(Exception):
    """The bundle cannot be applied — the caller must roll back."""


@dataclass
class TableStat:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0


@dataclass
class SyncReport:
    tables: Dict[str, TableStat] = field(default_factory=dict)
    changes: List[dict] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def stat(self, table: str) -> TableStat:
        return self.tables.setdefault(table, TableStat())

    def as_dict(self) -> dict:
        return {
            "tables": {t: vars(s) for t, s in self.tables.items()},
            "changes": self.changes,
            "warnings": self.warnings,
        }


def _json_safe(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _snapshot(obj) -> dict:
    return {c.key: getattr(obj, c.key) for c in obj.__table__.columns
            if c.key not in _IGNORED_COLS}


def _record(report: SyncReport, table: str, key: str,
            before: Optional[dict], after: dict) -> None:
    """Fold one object's before/after into the report."""
    stat = report.stat(table)
    if before is None:
        stat.created += 1
        return
    changed = [(k, before.get(k), after[k]) for k in after if before.get(k) != after[k]]
    if not changed:
        stat.unchanged += 1
        return
    stat.updated += 1
    for name, old, new in changed:
        if len(report.changes) < MAX_CHANGES:
            report.changes.append({"table": table, "key": key, "field": name,
                                   "from": _json_safe(old), "to": _json_safe(new)})


def apply_bundle(session, bundle: Bundle) -> SyncReport:
    """Apply every part of ``bundle``. Flushes; the caller commits or rolls back."""
    report = SyncReport()
    resolved = _apply_entities(session, bundle, report)
    _apply_builder(session, bundle, report, resolved)
    _apply_edges(session, bundle, report, resolved)
    _apply_signals(session, bundle, report)
    _apply_court_checks(session, bundle, report)
    return report


def _apply_entities(session, bundle: Bundle, report: SyncReport
                    ) -> Dict[Tuple[str, str], int]:
    """Upsert every entity; return a natural-key -> id map for the edge pass."""
    resolved: Dict[Tuple[str, str], int] = {}
    for e in bundle.entities:
        if e.kind == "company":
            existing = session.scalar(select(Entity).where(Entity.eik == e.eik))
            before = _snapshot(existing) if existing is not None else None
            ent, _ = entity_for_company(
                session, e.eik, name=e.name, legal_form=e.legal_form, status=e.status,
                address=e.address, capital_eur=e.capital_eur,
                founded_year=e.founded_year, source=e.source,
            )
            # The shared helper does not know about the seizure flag; apply it here.
            # `is not None` (not truthiness) so has_seizure=False genuinely clears it.
            for attr in ("has_seizure", "seizure_count", "seizure_last_at",
                         "seizure_source_url"):
                value = getattr(e, attr)
                if value is not None:
                    setattr(ent, attr, value)
            session.flush()

            _record(report, "entity", e.eik, before, _snapshot(ent))
            resolved[("eik", e.eik)] = ent.id
            continue

        prefix = e.person_key.split("-")[0]
        if prefix.isdigit() and session.scalar(
            select(Entity.id).where(Entity.eik == prefix, Entity.kind == "company")
        ):
            report.warnings.append(
                f"person_key {e.person_key} resolves to company ЕИК {prefix} — "
                "corporate shareholder listed as a person?"
            )
        existing = session.scalar(
            select(Entity).where(Entity.person_key == e.person_key)
        )
        before = _snapshot(existing) if existing is not None else None
        ent, _ = entity_for_person(session, e.name, e.person_key, source=e.source)
        _record(report, "entity", e.person_key, before, _snapshot(ent))
        resolved[("person_key", e.person_key)] = ent.id
    return resolved


def _apply_builder(session, bundle: Bundle, report: SyncReport,
                   resolved: Dict[Tuple[str, str], int]) -> None:
    b = bundle.builder
    if b is None:
        return
    existing = session.scalar(select(Builder).where(Builder.eik == b.eik))
    before = _snapshot(existing) if existing is not None else None
    builder = existing
    if builder is None:
        builder = Builder(eik=b.eik, name=b.name)
        session.add(builder)
    # enrich, don't erase
    for attr in ("name", "legal_form", "address", "capital_bgn", "status",
                 "ksb_category", "ksb_active", "insolvency_flag", "tax_debt_bgn"):
        value = getattr(b, attr)
        if value is not None:
            setattr(builder, attr, value)
    session.flush()
    entity_for_builder(session, builder)  # links builder.entity_id, mirrors identity
    session.flush()
    _record(report, "builder", b.eik, before, _snapshot(builder))


def _resolve_ref(session, ref: EntityRef, resolved: Dict[Tuple[str, str], int]) -> int:
    """Natural key -> entity id, preferring entities created in this bundle."""
    key = ("eik", ref.eik) if ref.eik else ("person_key", ref.person_key)
    if key in resolved:
        return resolved[key]
    column = Entity.eik if ref.eik else Entity.person_key
    entity = session.scalar(select(Entity).where(column == key[1]))
    if entity is None:
        raise BundleError(
            f"edge references unknown entity ({key[0]}={key[1]}) — include it in "
            "the bundle's entities, or push it first"
        )
    resolved[key] = entity.id
    return entity.id


def _apply_edges(session, bundle: Bundle, report: SyncReport,
                 resolved: Dict[Tuple[str, str], int]) -> None:
    for e in bundle.edges:
        src_id = _resolve_ref(session, e.src, resolved)
        dst_id = _resolve_ref(session, e.dst, resolved)
        existing = session.scalar(select(EntityEdge).where(and_(
            EntityEdge.src_entity_id == src_id,
            EntityEdge.dst_entity_id == dst_id,
            EntityEdge.relation == e.relation,
            EntityEdge.valid_from.is_(None) if e.valid_from is None
            else EntityEdge.valid_from == e.valid_from,
        )))
        before = _snapshot(existing) if existing is not None else None
        edge = upsert_edge(
            session, src_id, dst_id, e.relation, share_pct=e.share_pct, role=e.role,
            valid_from=e.valid_from, valid_to=e.valid_to, is_current=e.is_current,
            source=e.source,
        )
        _record(report, "entity_edge", f"{src_id}->{dst_id}:{e.relation}",
                before, _snapshot(edge))


def _apply_signals(session, bundle: Bundle, report: SyncReport) -> None:
    """Upsert on (url, matched_name).

    ``entity_id`` is resolved **per signal** from its own ЕИК / person_key — never
    from the url. One court act legitimately names several companies, and matching
    on the url alone reassigns every one of them to whichever entity came last.
    """
    for s in bundle.signals:
        entity_id = None
        if s.matched_eik:
            entity_id = session.scalar(
                select(Entity.id).where(Entity.eik == s.matched_eik)
            )
        if entity_id is None and s.matched_person_key:
            entity_id = session.scalar(
                select(Entity.id).where(Entity.person_key == s.matched_person_key)
            )

        existing = session.scalar(select(EntitySignal).where(and_(
            EntitySignal.url == s.url,
            EntitySignal.matched_name == s.matched_name,
        )))
        before = _snapshot(existing) if existing is not None else None
        signal = existing
        if signal is None:
            signal = EntitySignal(url=s.url, matched_name=s.matched_name,
                                  subject_kind=s.subject_kind, source_type=s.source_type,
                                  tier=s.tier, match_confidence=s.match_confidence)
            session.add(signal)
        for attr in ("subject_kind", "source_type", "tier", "match_confidence",
                     "matched_eik", "matched_person_key", "title", "snippet",
                     "source_site", "observed_date", "scraped_at"):
            value = getattr(s, attr)
            if value is not None:
                setattr(signal, attr, value)
        if entity_id is not None:
            signal.entity_id = entity_id
        session.flush()
        _record(report, "entity_signal", f"{s.url}|{s.matched_name}",
                before, _snapshot(signal))


def _apply_court_checks(session, bundle: Bundle, report: SyncReport) -> None:
    """Append-only log of searches performed.

    Keyed on the exact ``(eik, source_site, checked_at)`` triple so re-pushing the
    same bundle is a no-op, while a genuinely later check appends a new row.
    """
    for c in bundle.court_checks:
        existing = session.scalar(select(CourtCheck).where(and_(
            CourtCheck.eik == c.eik,
            CourtCheck.source_site == c.source_site,
            CourtCheck.checked_at == c.checked_at,
        )))
        if existing is not None:
            report.stat("court_check").skipped += 1
            continue
        session.add(CourtCheck(eik=c.eik, name=c.name, method=c.method,
                               acts_found=c.acts_found, source_site=c.source_site,
                               checked_at=c.checked_at))
        session.flush()
        report.stat("court_check").created += 1
