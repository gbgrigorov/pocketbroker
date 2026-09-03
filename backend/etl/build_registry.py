"""Build the canonical MVP neighbourhood registry from raw data and report coverage.

Run from the repo root:
    python3 -m backend.etl.build_registry

Writes ``backend/seeds/neighbourhoods.json`` (the 61 mappable neighbourhoods) and
prints a coverage report: how many price rows resolve, and an explicit list of
anything that does NOT resolve, so no data is dropped silently.
"""

from __future__ import annotations

import glob
import json
import os
from collections import Counter

from etl.neighbourhoods import NameResolver, build_canonical_registry

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CURRENT = os.path.join(REPO_ROOT, "data/raw/imot_bg/sofia_current_2026-05.jsonl")
HISTORY_GLOB = os.path.join(REPO_ROOT, "data/raw/imot_bg/sofia_history/*.jsonl")
CURRENT_RENT_GLOB = os.path.join(REPO_ROOT, "data/raw/imot_bg/sofia_current_rent_*.jsonl")
HISTORY_RENT_GLOB = os.path.join(REPO_ROOT, "data/raw/imot_bg/sofia_history_rent/*.jsonl")
GOLD = os.path.join(REPO_ROOT, "data/raw/gold/gold_eur_per_gram.jsonl")
MIN_WAGE = os.path.join(REPO_ROOT, "data/raw/macro/bg_min_wage.jsonl")
COORDS = os.path.join(REPO_ROOT, "data/raw/transport/sofia_neighbourhood_coords.json")
SEED_OUT = os.path.join(REPO_ROOT, "backend/seeds/neighbourhoods.json")

_RAW = os.path.join(REPO_ROOT, "data/raw/imot_bg")
_TRANSPORT = os.path.join(REPO_ROOT, "data/raw/transport")


def city_paths(slug: str) -> dict:
    """Resolve the raw-data file globs + coords path for an additional city.

    File-prefix convention (see crawlers): ``{slug}_current_2*.jsonl`` (sale),
    ``{slug}_current_rent_*.jsonl``, ``{slug}_history/*.jsonl``,
    ``{slug}_history_rent/*.jsonl``, ``{slug}_neighbourhood_coords.json``.
    """
    return {
        "current_glob": os.path.join(_RAW, f"{slug}_current_2*.jsonl"),
        "current_rent_glob": os.path.join(_RAW, f"{slug}_current_rent_*.jsonl"),
        "history_glob": os.path.join(_RAW, f"{slug}_history/*.jsonl"),
        "history_rent_glob": os.path.join(_RAW, f"{slug}_history_rent/*.jsonl"),
        "coords": os.path.join(_TRANSPORT, f"{slug}_neighbourhood_coords.json"),
    }


# Additional cities loaded incrementally (Sofia keeps the dedicated constants above).
CITIES = {
    "varna": {"name": "Варна", **city_paths("varna")},
    "burgas": {"name": "Бургас", **city_paths("burgas")},
    "plovdiv": {"name": "Пловдив", **city_paths("plovdiv")},
}

# Historical strings that don't casefold-match a current name. Curated for the
# MVP 61 only; extend as the coverage report surfaces real misses.
ALIASES: dict = {}


def load_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def main():
    # Sale + rent current snapshots together — a priced slug from either is mappable.
    current_records = list(load_jsonl(CURRENT))
    for path in sorted(glob.glob(CURRENT_RENT_GLOB)):
        current_records += list(load_jsonl(path))
    with open(COORDS, encoding="utf-8") as fh:
        coords = json.load(fh)

    registry = build_canonical_registry(current_records, coords)

    # Resolver keyed on canonical names of the MVP 61 (+ aliases for divergent strings)
    name_to_slug = {entry["name"]: slug for slug, entry in registry.items()}
    resolver = NameResolver(name_to_slug, ALIASES)

    # Resolve every historical row; count per canonical slug, collect unresolved names
    resolved_rows = 0
    total_rows = 0
    unresolved_names = Counter()
    per_slug = Counter()
    for path in sorted(glob.glob(HISTORY_GLOB)):
        for rec in load_jsonl(path):
            total_rows += 1
            slug = resolver.resolve(rec.get("neighborhood"))
            if slug is None:
                unresolved_names[rec.get("neighborhood")] += 1
            else:
                resolved_rows += 1
                per_slug[slug] += 1

    distinct_current = {r["neighborhood"] for r in current_records}

    print("=== Canonical MVP registry ===")
    print(f"current snapshot:        {len(current_records)} rows, {len(distinct_current)} distinct names")
    print(f"coords file:             {len(coords)} entries")
    print(f"canonical (price+coord): {len(registry)} neighbourhoods")
    print()
    print("=== Historical resolution (MVP 61 only) ===")
    print(f"historical rows total:   {total_rows}")
    print(f"resolved to an MVP 61:   {resolved_rows} ({resolved_rows*100//total_rows}%)")
    print(f"not in MVP 61 (dropped): {total_rows - resolved_rows} across {len(unresolved_names)} names")
    print()
    zero = sorted(slug for slug in registry if per_slug[slug] == 0)
    if zero:
        print(f"!! {len(zero)} MVP neighbourhoods with ZERO historical rows (investigate casing/alias):")
        for slug in zero:
            print(f"     {slug}  ({registry[slug]['name']})")
    else:
        print("all MVP neighbourhoods have >=1 historical row")
    print()
    print("top 10 unresolved historical names (NOT in MVP 61 — expected, listed for transparency):")
    for name, n in unresolved_names.most_common(10):
        print(f"     {n:5d}  {name}")

    os.makedirs(os.path.dirname(SEED_OUT), exist_ok=True)
    with open(SEED_OUT, "w", encoding="utf-8") as fh:
        json.dump(
            sorted(registry.values(), key=lambda e: e["slug"]),
            fh, ensure_ascii=False, indent=2,
        )
    print(f"\nwrote {SEED_OUT}")


if __name__ == "__main__":
    main()
