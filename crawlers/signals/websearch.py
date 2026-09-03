"""Web-search signal layer — per-developer / per-person query for public mentions.

For each target we ask a search engine for the name plus risk terms
(измама / фалит / недостроен / съд / жалба) and keep the top hits as ``web``-tier
signals (lowest confidence — a hit is a lead to verify, not proof).

v1 is run **once, by hand**, via the assistant's web-search capability: the
queries below are executed and their results saved to a raw JSONL through
``write_hits``. A search-API adapter can later replace the manual step for
automation — keep the ``search(query) -> list[hit]`` shape.

    # programmatic (future):
    from crawlers.signals.websearch import run
    run(targets, search_fn=my_api_adapter)

    # manual (v1):
    python3 -m crawlers.signals.websearch --from-json hits.json
"""

from __future__ import annotations

import datetime as _dt
import json
import secrets
from pathlib import Path
from typing import Iterable, List

from crawlers.signals import DATA_ROOT

RISK_TERMS = ["измама", "фалит", "недостроен", "съд", "дело", "жалба", "спрян строеж"]


def query_for(name: str) -> str:
    terms = " OR ".join(RISK_TERMS)
    return f'"{name}" ({terms})'


def write_hits(hits: Iterable[dict], scope: str = "sofia") -> Path:
    """Persist web hits as a raw signal file (matched later by the ETL)."""
    out_dir = DATA_ROOT / "raw" / "signals" / scope
    out_dir.mkdir(parents=True, exist_ok=True)
    today = _dt.date.today().isoformat()
    out_path = out_dir / f"web_{today}_{secrets.token_hex(4)}.jsonl"
    now = _dt.datetime.now(_dt.timezone.utc).isoformat()
    n = 0
    with out_path.open("w", encoding="utf-8") as fh:
        for h in hits:
            h.setdefault("source_site", "web")
            h.setdefault("scraped_at", now)
            fh.write(json.dumps(h, ensure_ascii=False) + "\n")
            n += 1
    print(f"web signals: wrote {n} hits -> {out_path}")
    return out_path


def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-json", required=True, help="JSON array of hit dicts")
    args = parser.parse_args()
    hits: List[dict] = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
    write_hits(hits)


if __name__ == "__main__":
    _cli()
