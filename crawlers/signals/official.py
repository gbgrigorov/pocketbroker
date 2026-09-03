"""Pure helpers for official-tier signals — no I/O, unit-testable.

``act_mentions_eik`` is the defamation-safety gate: an official record is kept
only when the company's ЕИК literally appears in the source text (digits may be
space-separated in court acts), and never as a substring of a longer number.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional


def act_mentions_eik(text: Optional[str], eik: str) -> bool:
    """True iff ``eik`` appears in ``text`` as a standalone number.

    Court acts often print the ЕИК with thin spaces ("175 155 346"); we collapse
    runs of digits+spaces and require an exact, boundary-delimited digit match.
    """
    if not text or not eik:
        return False
    digits = re.sub(r"\D", "", eik)
    if not digits:
        return False
    # Collapse "175 155 346" -> "175155346" everywhere, then word-boundary match.
    collapsed = re.sub(r"(?<=\d)[  .]+(?=\d)", "", text)
    return re.search(rf"(?<!\d){re.escape(digits)}(?!\d)", collapsed) is not None


def parse_bg_date(value: Optional[str]) -> Optional[date]:
    """Parse ISO ('2019-07-25') or dotted ('25.07.2019') dates; None otherwise."""
    if not value:
        return None
    value = value.strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})$", value)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{4})$", value)
        if not m:
            return None
        d, mo, y = map(int, m.groups())
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def to_registry_row(*, eik: str, name: str, url: str,
                    title: Optional[str], snippet: Optional[str],
                    observed: Optional[str]) -> dict:
    """Shape one confirmed act into a ``registry_*.jsonl`` row for ``load_registry``."""
    parsed = parse_bg_date(observed)
    return {
        "matched_eik": eik,
        "matched_name": name,
        "url": url,
        "title": title,
        "snippet": snippet,
        "source_site": "legalacts",
        "observed_date": parsed.isoformat() if parsed else None,
    }
