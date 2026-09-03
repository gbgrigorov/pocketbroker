"""Run the signal ETL: raw forum/web/registry signals -> entity_signal.

    cd backend && .venv/bin/python -m etl.run_signals

Idempotent (upsert on url + matched_name). Run after builders + ownership ETL so
the target set (companies + owner/manager persons) is populated.

Inputs (produced by the signal scrapers):
    data/raw/signals/<scope>/bgmamma_*.jsonl   (forum corpus)
    data/raw/signals/<scope>/web_*.jsonl       (web hits)
    data/raw/signals/<scope>/registry_*.jsonl  (ЕИК register lookups, optional)
    data/raw/signals/<scope>/legalacts_checks_*.jsonl  (court-search log -> court_check)
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

from app.db import SessionLocal
from etl.load_court_checks import CheckReport, load_checks
from etl.load_signals import (SignalReport, _build_targets, _seed_developers,
                              load_forum, load_registry, load_web)

DATA_ROOT = Path(__file__).resolve().parents[2] / "data"
SIGNALS = DATA_ROOT / "raw" / "signals"


def _load_jsonl(path: str):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def _glob(pattern: str):
    return sorted(glob.glob(str(SIGNALS / "**" / pattern), recursive=True))


def main() -> None:
    report = SignalReport()
    checks = CheckReport()
    session = SessionLocal()
    try:
        _seed_developers(session, report)
        targets = _build_targets(session)
        report.targets = len(targets)

        for path in _glob("bgmamma_*.jsonl"):
            load_forum(session, _load_jsonl(path), targets, report)
        for path in _glob("web_*.jsonl"):
            load_web(session, _load_jsonl(path), targets, report)
        for pat in ("registry_*.jsonl", "legalacts_*.jsonl"):
            for path in _glob(pat):
                # legalacts_checks_* are the search log, not acts — handled below.
                if "legalacts_checks_" in Path(path).name:
                    continue
                load_registry(session, _load_jsonl(path), report)

        # The court-search log: records that a search HAPPENED, zero results included.
        for path in _glob("legalacts_checks_*.jsonl"):
            load_checks(session, _load_jsonl(path), checks)

        session.commit()
    finally:
        session.close()

    print("=== signal ETL report ===")
    print(f"targets (companies+people): {report.targets}")
    print(f"developers seeded:          {report.seeded_developers}")
    print(f"forum signals:              {report.forum_signals}")
    print(f"web signals:                {report.web_signals}")
    print(f"registry signals:           {report.registry_signals}")
    print(f"skipped (already loaded):   {report.skipped_existing}")
    print(f"distinct flagged entities:  {len(report.flagged_entities)}")
    print(f"court checks logged:        {checks.checks_loaded} "
          f"(skipped {checks.skipped_existing} existing)")


if __name__ == "__main__":
    main()
