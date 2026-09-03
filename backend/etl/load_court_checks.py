"""Load ``court_check`` rows — the log of legalacts searches we actually ran.

A search that finds nothing writes no ``entity_signal`` row, so signal presence
can never answer "did we check this company?". The court runner emits one
``checks`` record per search — zero-result ones included — and this loads them.

Input files: ``data/raw/signals/<scope>/legalacts_checks_*.jsonl``

    {"eik": "120553098", "name": "НЕРА", "method": "eik",
     "acts_found": 8, "source_site": "legalacts.justice.bg",
     "checked_at": "2026-08-04T14:22:05"}

Each line is one *event*, so repeat checks accumulate and ``max(checked_at)``
per ЕИК is the last-checked date. Re-running the loader on the same file is
idempotent: a row is skipped when an identical (eik, method, checked_at) exists.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from sqlalchemy import select

from app.models import CourtCheck


@dataclass
class CheckReport:
    checks_loaded: int = 0
    skipped_existing: int = 0
    skipped_invalid: int = 0

    def __str__(self) -> str:
        return (
            "=== court-check ETL report ===\n"
            f"checks loaded:            {self.checks_loaded}\n"
            f"skipped (already loaded): {self.skipped_existing}\n"
            f"skipped (invalid):        {self.skipped_invalid}"
        )


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def iter_check_files(raw_dir: Path) -> Iterable[Path]:
    yield from sorted(raw_dir.glob("legalacts_checks_*.jsonl"))


def load_checks(session, rows: Iterable[dict], report: CheckReport) -> None:
    for row in rows:
        eik = (row.get("eik") or "").strip()
        checked = _parse_dt(row.get("checked_at"))
        if not eik or checked is None:
            report.skipped_invalid += 1
            continue
        method = row.get("method") or "eik"
        exists = session.scalar(
            select(CourtCheck.id).where(
                CourtCheck.eik == eik,
                CourtCheck.method == method,
                CourtCheck.checked_at == checked,
            )
        )
        if exists:
            report.skipped_existing += 1
            continue
        session.add(CourtCheck(
            eik=eik,
            name=row.get("name"),
            method=method,
            acts_found=int(row.get("acts_found") or 0),
            source_site=row.get("source_site") or "legalacts.justice.bg",
            checked_at=checked,
        ))
        report.checks_loaded += 1


def run(session, raw_dir: Path) -> CheckReport:
    report = CheckReport()
    for path in iter_check_files(raw_dir):
        with path.open(encoding="utf-8") as fh:
            rows = [json.loads(ln) for ln in fh if ln.strip()]
        load_checks(session, rows, report)
    session.commit()
    return report
