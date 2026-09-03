"""Show/hide rows in the "Reports & records" evidence feed (entity_signal.hidden).

A signal is crawler-matched evidence and can be wrong, outdated, or unfairly
amplify a builder's caution badge (directly, or via the sibling-company
rollup — see app.routes._sibling_official_subjects). This script lets you
switch individual signals — or an entire ownership/management network — on
or off without deleting the underlying evidence row.

    cd backend && .venv/bin/python -m etl.toggle_signal --find "жеков"
    .venv/bin/python -m etl.toggle_signal --id 280 --hide
    .venv/bin/python -m etl.toggle_signal --id 280 --show
    .venv/bin/python -m etl.toggle_signal --network 1363 --hide
    .venv/bin/python -m etl.toggle_signal --network 1363 --show
"""

from __future__ import annotations

import argparse

from sqlalchemy import or_, select

from app.db import SessionLocal
from app.models import Entity, EntityEdge, EntitySignal


def _find(session, text: str) -> None:
    needle = f"%{text}%"
    stmt = (
        select(EntitySignal, Entity.name)
        .join(Entity, Entity.id == EntitySignal.entity_id, isouter=True)
        .where(or_(
            EntitySignal.matched_name.ilike(needle),
            EntitySignal.matched_eik.ilike(needle),
            EntitySignal.title.ilike(needle),
            EntitySignal.url.ilike(needle),
            Entity.name.ilike(needle),
        ))
    )
    rows = session.execute(stmt).all()
    if not rows:
        print("No matching signals.")
        return
    for s, entity_name in rows:
        flag = "hidden" if s.hidden else "visible"
        print(f"id={s.id:<5} entity={s.entity_id} ({entity_name}) [{flag}] "
              f"{s.tier}: {s.title or s.matched_name}")


def _network_ids(session, entity_id: int) -> set:
    ids = {entity_id}
    rows = session.execute(
        select(EntityEdge.dst_entity_id)
        .where(EntityEdge.src_entity_id == entity_id,
               EntityEdge.relation.in_(("ownership", "management")))
    )
    ids.update(r[0] for r in rows)
    return ids


def _toggle_id(session, signal_id: int, hidden: bool) -> None:
    signal = session.get(EntitySignal, signal_id)
    if signal is None:
        raise SystemExit(f"No entity_signal with id={signal_id}")
    signal.hidden = hidden
    session.commit()
    print(f"id={signal.id}: hidden={hidden} — {signal.title or signal.matched_name}")


def _toggle_network(session, entity_id: int, hidden: bool) -> None:
    ids = _network_ids(session, entity_id)
    signals = session.scalars(
        select(EntitySignal).where(EntitySignal.entity_id.in_(ids))
    ).all()
    if not signals:
        print(f"No signals found for entity {entity_id} or its network ({len(ids)} entities).")
        return
    counts: dict = {}
    for s in signals:
        s.hidden = hidden
        counts[s.entity_id] = counts.get(s.entity_id, 0) + 1
    session.commit()
    names = {e.id: e.name for e in session.scalars(
        select(Entity).where(Entity.id.in_(counts))
    ).all()}
    for eid, n in sorted(counts.items()):
        print(f"entity {eid} ({names.get(eid)}): {n} signal(s) -> hidden={hidden}")
    print(f"Total: {len(signals)} signal(s) across {len(counts)} entit(y/ies).")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--find", metavar="TEXT",
                        help="list signals matching TEXT (name/ЕИК/title/url)")
    parser.add_argument("--id", type=int, metavar="SIGNAL_ID",
                        help="target a single entity_signal row")
    parser.add_argument("--network", type=int, metavar="ENTITY_ID",
                        help="target ENTITY_ID plus every entity it owns/manages")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--hide", action="store_true", help="set hidden = true")
    group.add_argument("--show", action="store_true", help="set hidden = false")
    args = parser.parse_args()

    session = SessionLocal()
    try:
        if args.find:
            _find(session, args.find)
            return
        if args.hide == args.show:
            raise SystemExit("Specify exactly one of --hide / --show")
        hidden = args.hide
        if args.id is not None:
            _toggle_id(session, args.id, hidden)
        elif args.network is not None:
            _toggle_network(session, args.network, hidden)
        else:
            raise SystemExit("Specify --find, --id, or --network")
    finally:
        session.close()


if __name__ == "__main__":
    main()
