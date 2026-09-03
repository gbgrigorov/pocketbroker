"""Natural-key entity helpers — get-or-create companies, persons and edges.

Shared by the ETL (batch loads from ``data/raw``) and the sync API (bundles
pushed from the MacBook). Every function is idempotent on a natural key —
ЕИК for companies, ``person_key`` for persons, ``(src, dst, relation,
valid_from)`` for edges — and enriches an existing row rather than replacing it,
so re-running is always safe.
"""

from __future__ import annotations

from datetime import date
from typing import Optional, Tuple

from sqlalchemy import and_, select

from app.models import Builder, Entity, EntityEdge
from app.names import norm_name as _norm_name
from app.slugs import slugify

BGN_PER_EUR = 1.95583  # fixed peg (matches the crawlers)


def entity_for_builder(session, builder: Builder) -> Entity:
    """Get-or-create the company :class:`Entity` backing ``builder`` and link it.

    Idempotent: matches an existing entity by ``builder.entity_id`` first, then
    by ЕИК, before creating a new one. Builder identity fields are mirrored onto
    the node so the graph view stands alone.
    """
    entity: Optional[Entity] = None
    if builder.entity_id is not None:
        entity = session.get(Entity, builder.entity_id)
    if entity is None and builder.eik:
        entity = session.scalar(select(Entity).where(Entity.eik == builder.eik))
    if entity is None:
        entity = Entity(kind="company", eik=builder.eik)
        session.add(entity)

    entity.kind = "company"
    entity.is_builder = True
    entity.name = builder.name
    entity.name_normalized = _norm_name(builder.name)
    entity.slug = slugify(builder.name)
    entity.legal_form = builder.legal_form
    entity.status = builder.status
    entity.address = builder.address
    entity.capital_bgn = builder.capital_bgn
    entity.source = "ksb"
    session.flush()  # assign entity.id

    builder.entity_id = entity.id
    return entity


def entity_for_company(
    session, eik: str, *, name: Optional[str] = None, legal_form: Optional[str] = None,
    status: Optional[str] = None, address: Optional[str] = None,
    capital_eur: Optional[float] = None, founded_year: Optional[int] = None,
    source: Optional[str] = None,
) -> Tuple[Entity, bool]:
    """Get-or-create a company entity by ЕИК. Returns ``(entity, created)``.

    An existing node (e.g. a builder) is enriched, never duplicated or demoted —
    ``is_builder`` and a curated name are preserved.
    """
    entity = session.scalar(select(Entity).where(Entity.eik == eik))
    created = entity is None
    if entity is None:
        entity = Entity(kind="company", eik=eik, name=name or eik, is_builder=False,
                         slug=slugify(name or eik))
        session.add(entity)
    entity.kind = "company"
    if name:
        entity.name = name
        entity.name_normalized = _norm_name(name)
        entity.slug = slugify(name)
    if legal_form:
        entity.legal_form = legal_form
    if status:
        entity.status = status
    if address:
        entity.address = address
    if capital_eur is not None:
        entity.capital_bgn = round(capital_eur * BGN_PER_EUR, 2)
    if founded_year is not None:
        entity.founded_year = founded_year
    if source:
        entity.source = source
    session.flush()
    return entity, created


def entity_for_person(
    session, name: str, person_key: Optional[str], *, source: Optional[str] = None,
) -> Tuple[Entity, bool]:
    """Get-or-create a person entity by ``person_key``. Returns ``(entity, created)``.

    Persons have no ЕИК; dedup is by ``person_key`` (Papagal's stable person hash).
    Conservative: without a key, each occurrence is a distinct node.

    Some Papagal pages list a company's own quoted legal name in its "related
    persons" section, with a synthetic ``person_key`` of the form ``<eik>-N``.
    If that ``<eik>`` belongs to an existing company entity, resolve to it
    instead of creating a misclassified person duplicate.
    """
    if person_key:
        eik_prefix = person_key.split("-")[0]
        if eik_prefix.isdigit():
            company = session.scalar(
                select(Entity).where(Entity.eik == eik_prefix, Entity.kind == "company")
            )
            if company is not None:
                return company, False

    entity = None
    if person_key:
        entity = session.scalar(select(Entity).where(Entity.person_key == person_key))
    created = entity is None
    if entity is None:
        entity = Entity(kind="person", person_key=person_key, name=name,
                        name_normalized=_norm_name(name), slug=slugify(name), source=source)
        session.add(entity)
    elif name and not entity.name:
        entity.name = name
        entity.slug = slugify(name)
    session.flush()
    return entity, created


def upsert_edge(
    session,
    src_entity_id: int,
    dst_entity_id: int,
    relation: str,
    *,
    share_pct: Optional[float] = None,
    role: Optional[str] = None,
    valid_from: Optional[date] = None,
    valid_to: Optional[date] = None,
    is_current: bool = True,
    source: Optional[str] = None,
) -> EntityEdge:
    """Idempotent upsert of a directed edge on ``(src, dst, relation, valid_from)``.

    Re-running with the same key updates attributes in place rather than adding a
    duplicate row (NULL ``valid_from`` matched explicitly, since SQL NULL != NULL).
    """
    edge = session.scalar(
        select(EntityEdge).where(and_(
            EntityEdge.src_entity_id == src_entity_id,
            EntityEdge.dst_entity_id == dst_entity_id,
            EntityEdge.relation == relation,
            EntityEdge.valid_from.is_(None) if valid_from is None
            else EntityEdge.valid_from == valid_from,
        ))
    )
    if edge is None:
        edge = EntityEdge(
            src_entity_id=src_entity_id, dst_entity_id=dst_entity_id,
            relation=relation, valid_from=valid_from,
        )
        session.add(edge)
    edge.share_pct = share_pct
    edge.role = role
    edge.valid_to = valid_to
    edge.is_current = is_current
    edge.source = source
    session.flush()
    return edge
