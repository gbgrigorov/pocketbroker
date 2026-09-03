"""Signal ETL — match raw public sources to known developers/people, load evidence.

Pipeline position: runs *after* builders + ownership are in the DB. It:

1. builds the **target set** — every builder (company) + every owner/manager
   person in the graph, plus any new-building ``developer_name`` not yet a node
   (seeded so the developer gets a profile page),
2. reads the raw signal files under ``data/raw/signals/<scope>/``:
     - ``bgmamma_*.jsonl``  forum posts   -> community tier (fuzzy name match)
     - ``web_*.jsonl``      web hits      -> web tier        (attached by name)
     - ``registry_*.jsonl`` ЕИК lookups   -> official tier   (exact ЕИК match)
3. runs the conservative name matcher and **upserts** ``entity_signal`` rows
   (key: url + matched_name), resolving ``entity_id`` by ЕИК → person_key → name.

Idempotent — safe to re-run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, Iterable, List, Optional

from sqlalchemy import select

from app.models import Builder, Entity, EntitySignal, NewBuilding
from app.slugs import slugify
from etl.entities import entity_for_builder
from etl.load_phase3 import _norm_name

# Repo-root import of the pure matcher (crawlers is standalone, no DB).
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from crawlers.signals.match import Target, find_mentions, index_targets  # noqa: E402

# Developer names that resolve to a known ЕИК (from the КСБ register) but may not
# yet be loaded as builders. Lets the named developers get a profile + page.
KNOWN_DEV_EIK = {
    "артекс инженеринг": "175155346",
}

_BG_MONTHS = {
    "ян": 1, "фев": 2, "мар": 3, "апр": 4, "май": 5, "юни": 6, "юли": 7,
    "авг": 8, "септ": 9, "сеп": 9, "окт": 10, "ное": 11, "ноем": 11, "дек": 12,
}


@dataclass
class SignalReport:
    targets: int = 0
    seeded_developers: int = 0
    forum_signals: int = 0
    web_signals: int = 0
    registry_signals: int = 0
    skipped_existing: int = 0
    flagged_entities: set = field(default_factory=set)
    seen: set = field(default_factory=set)  # (url, matched_name) within this run


def _parse_bg_date(value: Optional[str]) -> Optional[date]:
    """'25 юли 2019,  11:09 ч.' -> date(2019, 7, 25); best-effort, None on miss."""
    if not value:
        return None
    m = re.match(r"(\d{1,2})\s+([а-я]+)\.?\s+(\d{4})", value.strip().lower())
    if not m:
        return None
    day, mon_word, year = m.groups()
    for prefix, num in _BG_MONTHS.items():
        if mon_word.startswith(prefix):
            try:
                return date(int(year), num, int(day))
            except ValueError:
                return None
    return None


# --- target set -------------------------------------------------------------

def _seed_developers(session, report: SignalReport) -> None:
    """Ensure each new-building developer is a node (so it can carry signals)."""
    names = {
        n for (n,) in session.execute(
            select(NewBuilding.developer_name).where(NewBuilding.developer_name.is_not(None))
        )
    }
    for name in names:
        key = _norm_name(name)
        if not key:
            continue
        exists = session.scalar(select(Entity).where(Entity.name_normalized == key))
        if exists is not None:
            continue
        eik = KNOWN_DEV_EIK.get(key)
        builder = None
        if eik:
            builder = session.scalar(select(Builder).where(Builder.eik == eik))
            if builder is None:
                builder = Builder(eik=eik, name=name)
                session.add(builder)
                session.flush()
            entity_for_builder(session, builder)
        else:
            # No ЕИК yet — store as a plain company node so signals still attach.
            session.add(Entity(kind="company", name=name, name_normalized=key, slug=slugify(name),
                               is_builder=True, source="new_building"))
        report.seeded_developers += 1
    session.flush()


def _build_targets(session) -> List[Target]:
    """Match only entities we actually care about: builders + the people behind
    them. Random companies / NGOs in the graph are excluded to avoid noise.
    """
    from app.models import EntityEdge

    builder_ids = {
        bid for (bid,) in session.execute(
            select(Entity.id).where(Entity.is_builder.is_(True))
        )
    }
    # Persons who own/manage a builder (the "people behind the developer").
    people_ids = {
        sid for (sid,) in session.execute(
            select(EntityEdge.src_entity_id)
            .join(Entity, Entity.id == EntityEdge.dst_entity_id)
            .where(Entity.is_builder.is_(True))
        )
    }
    keep = builder_ids | people_ids
    targets: List[Target] = []
    for e in session.scalars(select(Entity).where(Entity.id.in_(keep))):
        targets.append(Target(
            name=e.name, kind=e.kind, eik=e.eik,
            person_key=e.person_key, entity_id=e.id,
        ))
    # Prune company tokens shared by many builders (проект/българия/билдинг…).
    return index_targets(targets)


def _entity_lookup(session):
    by_eik = {e.eik: e.id for e in session.scalars(select(Entity)) if e.eik}
    by_pkey = {e.person_key: e.id for e in session.scalars(select(Entity)) if e.person_key}
    by_name: Dict[str, int] = {}
    for e in session.scalars(select(Entity)):
        if e.name_normalized:
            by_name.setdefault(e.name_normalized, e.id)
    return by_eik, by_pkey, by_name


# --- upsert -----------------------------------------------------------------

def _upsert(session, report: SignalReport, *, url: str, matched_name: str,
            subject_kind: str, source_type: str, tier: str, confidence: str,
            title: Optional[str], snippet: Optional[str], source_site: Optional[str],
            observed: Optional[date], scraped: Optional[datetime],
            entity_id: Optional[int], eik: Optional[str], pkey: Optional[str],
            hidden: bool = False) -> bool:
    pair = (url, matched_name)
    if pair in report.seen:
        return False
    report.seen.add(pair)
    existing = session.scalar(
        select(EntitySignal).where(
            EntitySignal.url == url, EntitySignal.matched_name == matched_name
        )
    )
    if existing is not None:
        report.skipped_existing += 1
        return False
    session.add(EntitySignal(
        entity_id=entity_id, subject_kind=subject_kind, matched_name=matched_name,
        matched_eik=eik, matched_person_key=pkey, source_type=source_type, tier=tier,
        match_confidence=confidence, title=title, snippet=snippet, url=url,
        source_site=source_site, observed_date=observed, scraped_at=scraped,
        hidden=hidden,
    ))
    if entity_id is not None:
        report.flagged_entities.add(entity_id)
    return True


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


# --- layers -----------------------------------------------------------------

def load_forum(session, posts: Iterable[dict], targets: List[Target],
               report: SignalReport) -> None:
    for post in posts:
        text = post.get("text") or ""
        url = post.get("url")
        if not url:
            continue
        # Skip the machine-generated Q&A summary post (it lists many firm names
        # and would manufacture spurious "mentions").
        if text.startswith("Q&A") or "генерират машинно" in text[:400]:
            continue
        observed = _parse_bg_date(post.get("post_date"))
        scraped = _parse_dt(post.get("scraped_at"))
        for mention in find_mentions(text, targets):
            t = mention.target
            if _upsert(
                session, report, url=url, matched_name=t.name, subject_kind=t.kind,
                source_type="forum", tier="community", confidence=mention.confidence,
                title=f"BG-Mamma — тема {post.get('thread')}", snippet=mention.snippet,
                source_site="bgmamma", observed=observed, scraped=scraped,
                entity_id=t.entity_id, eik=t.eik, pkey=t.person_key,
            ):
                report.forum_signals += 1


def load_web(session, hits: Iterable[dict], targets: List[Target],
             report: SignalReport) -> None:
    by_norm = {_norm_name(t.name): t for t in targets}
    for hit in hits:
        url = hit.get("url")
        name = hit.get("matched_name")
        if not url or not name:
            continue
        t = by_norm.get(_norm_name(name))
        observed = None
        if hit.get("observed_date"):
            try:
                observed = date.fromisoformat(hit["observed_date"][:10])
            except (ValueError, TypeError):
                observed = None
        if _upsert(
            session, report, url=url, matched_name=name,
            subject_kind=hit.get("subject_kind") or (t.kind if t else "company"),
            source_type="web", tier="web", confidence="fuzzy_low",
            title=hit.get("title"), snippet=hit.get("snippet"),
            source_site=hit.get("source_site") or "web", observed=observed,
            scraped=_parse_dt(hit.get("scraped_at")),
            entity_id=t.entity_id if t else None,
            eik=t.eik if t else None, pkey=t.person_key if t else None,
        ):
            report.web_signals += 1


def load_registry(session, rows: Iterable[dict], report: SignalReport) -> None:
    """Official-tier signals keyed on ЕИК (insolvency/court register lookups)."""
    by_eik, _, _ = _entity_lookup(session)
    for row in rows:
        eik = row.get("matched_eik") or row.get("eik")
        url = row.get("url")
        if not eik or not url:
            continue
        if _upsert(
            session, report, url=url, matched_name=row.get("matched_name") or eik,
            subject_kind="company", source_type="registry", tier="official",
            confidence="eik", title=row.get("title"), snippet=row.get("snippet"),
            source_site=row.get("source_site") or "registry",
            observed=date.fromisoformat(row["observed_date"][:10]) if row.get("observed_date") else None,
            scraped=_parse_dt(row.get("scraped_at")), entity_id=by_eik.get(eik),
            eik=eik, pkey=None, hidden=bool(row.get("hidden")),
        ):
            report.registry_signals += 1
