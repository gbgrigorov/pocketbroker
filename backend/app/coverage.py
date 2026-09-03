"""Coverage flags for a set of research requests.

Answers two questions the admin inbox and the sync client both ask: do we hold
this company, and when did we last run a court search for its ЕИК?

The court flag reads ``court_check`` — the log of searches performed — **not**
signal presence. A search that finds no acts writes no signal and would
otherwise look like "never checked".
"""

from __future__ import annotations

from typing import Dict, List

from sqlalchemy import func, select

from app.models import CourtCheck, Entity, EntityEdge, ResearchRequest


def coverage_flags(session, requests: List[ResearchRequest]) -> Dict[int, dict]:
    """Map ``request.id`` -> coverage dict. Requests without an ЕИК get zeroes."""
    blank = {"in_db": False, "entity_id": None, "edge_count": 0,
             "court_checked_at": None, "court_acts": None}
    eiks = {r.company_eik for r in requests if r.company_eik}
    if not eiks:
        return {r.id: dict(blank) for r in requests}

    entities = {
        e.eik: e for e in session.scalars(select(Entity).where(Entity.eik.in_(eiks))).all()
    }
    edges: Dict[int, int] = {}
    ids = [e.id for e in entities.values()]
    if ids:
        src = select(EntityEdge.src_entity_id.label("eid"), func.count().label("n")) \
            .where(EntityEdge.src_entity_id.in_(ids)).group_by(EntityEdge.src_entity_id)
        dst = select(EntityEdge.dst_entity_id.label("eid"), func.count().label("n")) \
            .where(EntityEdge.dst_entity_id.in_(ids)).group_by(EntityEdge.dst_entity_id)
        for eid, n in session.execute(src.union_all(dst)).all():
            edges[eid] = edges.get(eid, 0) + n

    # Latest check per ЕИК: newest checked_at wins, with that run's act count.
    checks: Dict[str, tuple] = {}
    rows = session.execute(
        select(CourtCheck.eik, CourtCheck.checked_at, CourtCheck.acts_found)
        .where(CourtCheck.eik.in_(eiks))
        .order_by(CourtCheck.eik, CourtCheck.checked_at.desc())
    ).all()
    for eik, checked_at, acts in rows:
        if eik not in checks:
            checks[eik] = (checked_at, acts)

    out: Dict[int, dict] = {}
    for r in requests:
        flags = dict(blank)
        ent = entities.get(r.company_eik) if r.company_eik else None
        if ent is not None:
            flags["in_db"] = True
            flags["entity_id"] = ent.id
            flags["edge_count"] = edges.get(ent.id, 0)
        if r.company_eik and r.company_eik in checks:
            flags["court_checked_at"], flags["court_acts"] = checks[r.company_eik]
        out[r.id] = flags
    return out
