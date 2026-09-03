"""Loose name normalisation, shared by the API and the ETL.

Lives in ``app`` rather than ``etl`` so the deployed API never has to import the
ETL package. ``etl.load_phase3`` re-exports it as ``_norm_name`` for its callers.
"""

from __future__ import annotations

import re
from typing import Optional


def norm_name(name: Optional[str]) -> str:
    """Loose company-name key for matching a project's developer to a builder."""
    if not name:
        return ""
    name = re.sub(r"[\"'„“”«»]", "", name.lower())
    # drop common legal-form suffixes
    name = re.sub(r"\b(оод|еоод|ад|еад|ет|кд|сд|ltd|ood|eood|ad|ead)\b", " ", name)
    return re.sub(r"\s+", " ", name).strip()
