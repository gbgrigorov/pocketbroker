"""Canonical neighbourhood registry + historical name resolution.

Phase 2.0 data foundation. The current imot.bg snapshot has slugs and proper
title-case Bulgarian names; the 31 years of historical snapshots have NO slugs
and use inconsistent casing (e.g. ALL-CAPS "БАНИШОРА") and occasionally a
different string entirely (e.g. "БЕЛИ БРЕЗИ" vs current "Белите брези"). This
module resolves any historical name back to a canonical slug so no price row is
silently dropped.
"""

from __future__ import annotations

from typing import Dict, List, Optional


class NameResolver:
    """Resolves a raw neighbourhood name (any casing/source) to a canonical slug."""

    def __init__(self, name_to_slug, aliases=None):
        self._exact = {self._norm(name): slug for name, slug in name_to_slug.items()}
        self._aliases = {self._norm(name): slug for name, slug in (aliases or {}).items()}

    @staticmethod
    def _norm(name: str) -> str:
        return name.strip().casefold()

    def resolve(self, raw_name: Optional[str]) -> Optional[str]:
        if raw_name is None:
            return None
        key = self._norm(raw_name)
        if key in self._aliases:
            return self._aliases[key]
        return self._exact.get(key)


def build_canonical_registry(current_records: List[dict], coords: Dict[str, dict]) -> Dict[str, dict]:
    """Canonical MVP registry: slugs present in BOTH the current price snapshot and the coords file.

    Returns ``{slug: {slug, name, lat, lon, coord_source}}``. A neighbourhood is
    mappable only if it has both a price (current snapshot) and a coordinate.
    """
    priced_slugs = {
        r["neighborhood_slug"]: r["neighborhood"]
        for r in current_records
        if r.get("neighborhood_slug")
    }
    registry: Dict[str, dict] = {}
    for slug, name in priced_slugs.items():
        coord = coords.get(slug)
        if coord is None:
            continue
        registry[slug] = {
            "slug": slug,
            "name": name,
            "lat": coord["lat"],
            "lon": coord["lon"],
            "coord_source": coord.get("source"),
        }
    return registry
