"""Sync endpoints — the MacBook's window onto production.

Mounted at ``/api/admin/sync`` and gated by :func:`require_sync_token`. Nginx
refuses this prefix from the internet; the client reaches it through an SSH
tunnel (see ``deploy/SYNC_API.md``).

Nothing here touches ``user`` or ``oauth_account``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from app.coverage import coverage_flags
from app.db import get_session
from app.models import (CourtCheck, Entity, EntityEdge, EntitySignal, ResearchRequest,
                        SyncLog)
from app.sync.auth import require_sync_token
from app.sync.schemas import Bundle
from app.sync.upsert import BundleError, apply_bundle

router = APIRouter(
    prefix="/api/admin/sync",
    tags=["sync"],
    dependencies=[Depends(require_sync_token)],
)


@router.get("/requests")
def list_requests(
    status: str = Query("new", description="a status value, or 'all'"),
    limit: int = Query(200, ge=1, le=2000),
    session=Depends(get_session),
):
    """Requests waiting for research, newest first, with coverage flags."""
    stmt = select(ResearchRequest).order_by(ResearchRequest.created_at.desc()).limit(limit)
    if status != "all":
        stmt = stmt.where(ResearchRequest.status == status)
    requests = session.scalars(stmt).all()
    flags = coverage_flags(session, requests)
    return [
        {
            "id": r.id, "company_name": r.company_name, "company_eik": r.company_eik,
            "owner": r.owner, "details": r.details, "search_query": r.search_query,
            "requester_name": r.requester_name, "requester_email": r.requester_email,
            "status": r.status, "order_type": r.order_type, "scope": r.scope,
            "search_type": r.search_type, "network_depth": r.network_depth,
            "entity_count": r.entity_count,
            "price_eur": float(r.price_eur) if r.price_eur is not None else None,
            "expedited": r.expedited, "created_at": r.created_at,
            "delivered_at": r.delivered_at,
            **flags[r.id],
        }
        for r in requests
    ]


@router.post("/requests/{request_id}/claim")
def claim_request(request_id: int, session=Depends(get_session)):
    """Mark a request as being worked on. Idempotent; refuses a delivered one."""
    req = session.get(ResearchRequest, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="unknown request")
    if req.status == "delivered":
        raise HTTPException(status_code=409, detail="request already delivered")
    req.status = "in_progress"
    session.commit()
    return {"id": req.id, "status": req.status}


@router.get("/entities")
def lookup_entities(
    eik: List[str] = Query(default=[]),
    session=Depends(get_session),
):
    """What production already holds per ЕИК — so a push can be diffed first."""
    out: dict[str, Optional[dict]] = {e: None for e in eik}
    if not eik:
        return out
    for entity in session.scalars(select(Entity).where(Entity.eik.in_(eik))).all():
        edge_count = session.scalar(
            select(func.count()).select_from(EntityEdge).where(
                (EntityEdge.src_entity_id == entity.id)
                | (EntityEdge.dst_entity_id == entity.id)
            )
        )
        signal_count = session.scalar(
            select(func.count()).select_from(EntitySignal)
            .where(EntitySignal.entity_id == entity.id)
        )
        last_check = session.scalar(
            select(func.max(CourtCheck.checked_at)).where(CourtCheck.eik == entity.eik)
        )
        out[entity.eik] = {
            "id": entity.id, "name": entity.name, "kind": entity.kind,
            "is_builder": entity.is_builder, "status": entity.status,
            "legal_form": entity.legal_form, "founded_year": entity.founded_year,
            "edge_count": edge_count, "signal_count": signal_count,
            "last_court_check": last_check,
        }
    return out


def _run_bundle(session, bundle: Bundle, *, dry_run: bool, action: str,
                req: Optional[ResearchRequest]) -> dict:
    """Apply a bundle and log it.

    A dry run must leave nothing from the bundle behind but must still be
    recorded, so the order is: apply -> capture the report -> roll back -> log.
    A real apply commits the bundle, the request update and the log together.
    """
    try:
        report = apply_bundle(session, bundle)
    except BundleError as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    summary = report.as_dict()

    if dry_run:
        session.rollback()
    else:
        if req is not None:
            if bundle.report_md:
                req.report_md = bundle.report_md
            if bundle.notes:
                req.notes = bundle.notes
            req.status = "delivered"
            req.delivered_at = datetime.now(timezone.utc).replace(tzinfo=None)

    session.add(SyncLog(request_id=req.id if req is not None else None,
                        action=action, dry_run=dry_run, summary=summary))
    session.commit()

    if not dry_run:
        # /map, /cities and /entities are served from module-level caches, so a
        # push lands in the database but stays invisible to search and the map
        # until they are dropped. Imported here rather than at module scope to
        # keep the import graph one-directional (main mounts routes first).
        from app.routes import clear_caches
        clear_caches()

    return {"dry_run": dry_run,
            "request_id": req.id if req is not None else None,
            "status": req.status if req is not None else None,
            **summary}


@router.post("/requests/{request_id}/findings")
def push_findings(
    request_id: int,
    bundle: Bundle,
    dry_run: bool = Query(True, description="default true — nothing is written"),
    session=Depends(get_session),
):
    """Apply a findings bundle and mark the request delivered."""
    req = session.get(ResearchRequest, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="unknown request")
    return _run_bundle(session, bundle, dry_run=dry_run, action="findings", req=req)


@router.post("/bundle")
def push_bundle(
    bundle: Bundle,
    dry_run: bool = Query(True, description="default true — nothing is written"),
    session=Depends(get_session),
):
    """Apply a bundle not tied to any request — bulk/crawl data.

    This is what replaces the old ``deploy/ENTITY_PUSH.md`` CSV mirror.
    """
    return _run_bundle(session, bundle, dry_run=dry_run, action="bundle", req=None)
