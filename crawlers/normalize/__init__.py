"""Normalizers — merge raw per-site JSONL into canonical, deduped records.

Two stages, both dependency-free (stdlib only, so they run under either the
system python3 or backend/.venv):

- ``builders``      — canonicalise construction companies on ЕИК.
- ``new_buildings`` — entity-resolve the same project listed under different
  names across sites into one canonical project + a ``sources[]`` trail.

Reads from ``data/raw/<domain>/<scope>/`` and writes to
``data/normalized/<domain>/<scope>.jsonl``.
"""

from __future__ import annotations

from pathlib import Path

# repo_root/data  (this file is repo_root/crawlers/normalize/__init__.py)
DATA_ROOT = Path(__file__).resolve().parents[2] / "data"
