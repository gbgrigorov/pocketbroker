"""New-building normalizer — collapse the same project across sites into one record.

The same development is listed under different names on different portals
("Luxury Skyscraper" vs "Top Skyscraper"). This merges them via fuzzy name
matching within a (city, neighbourhood) block, keeping every site listing as a
``sources[]`` entry so nothing is lost and prices can be reconciled.

Dependency-free: uses stdlib ``difflib`` for similarity (no rapidfuzz install).

    python3 -m crawlers.normalize.new_buildings --city sofia [--threshold 0.82]

Input  : data/raw/new_buildings/<city>/*.jsonl   (raw, one row per site listing)
Output : data/normalized/new_buildings/<city>.jsonl  (canonical projects)
"""

from __future__ import annotations

import argparse
import glob
import json
import re
from difflib import SequenceMatcher
from statistics import median
from typing import Iterable, List, Optional

from crawlers.normalize import DATA_ROOT

# Generic words that carry no identity — stripped before comparing names.
_STOPWORDS = {
    "комплекс", "жилищна", "жилищен", "сграда", "сгради", "ново", "строителство",
    "residential", "complex", "building", "project", "проект", "к-с", "жк", "ж.к",
    "apartments", "апартаменти", "the", "of", "in", "на", "за",
}
_NON_WORD = re.compile(r"[^\wЀ-ӿ]+", re.UNICODE)


def _tokens(name: str) -> List[str]:
    cleaned = _NON_WORD.sub(" ", (name or "").lower())
    return [t for t in cleaned.split() if t and t not in _STOPWORDS]


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio() if (a or b) else 0.0


def name_similarity(a: str, b: str) -> float:
    """Robust name similarity in [0, 1] using stdlib difflib only.

    Combines three signals (max wins) so that real-world listing variants merge:
      1. token-set ratio (fuzzywuzzy-style) — order-independent, tolerates extras;
      2. de-spaced character ratio — handles "Sky Fort" vs "SkyFort";
      3. containment — one name's significant chars fully inside the other
         (e.g. extra neighbourhood token: "SkyFort Residence" ⊂ "SkyFort Residence Lozenets").
    """
    ta, tb = set(_tokens(a)), set(_tokens(b))
    if not ta or not tb:
        return 0.0

    inter = sorted(ta & tb)
    s_inter = " ".join(inter)
    s_a = " ".join(inter + sorted(ta - tb))
    s_b = " ".join(inter + sorted(tb - ta))
    token_set = max(_ratio(s_inter, s_a), _ratio(s_inter, s_b), _ratio(s_a, s_b)) if inter \
        else _ratio(" ".join(sorted(ta)), " ".join(sorted(tb)))

    da, db = "".join(_tokens(a)), "".join(_tokens(b))
    char_ratio = _ratio(da, db)

    short, long = sorted((da, db), key=len)
    containment = 1.0 if (len(short) >= 6 and short in long and len(short) / len(long) >= 0.6) else 0.0

    return max(token_set, char_ratio, containment)


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _NON_WORD.sub("-", (text or "").lower())).strip("-")[:60]


def load_jsonl(path: str) -> Iterable[dict]:
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


_CYRILLIC = re.compile(r"[Ѐ-ӿ]")
_LATIN = re.compile(r"[A-Za-z]")


def _script(text: str) -> str:
    """Rough script of a string: 'cyr', 'lat', or 'mixed'/'none' — used to decide
    whether two developer names are even comparable (Cyrillic vs transliterated Latin)."""
    has_c, has_l = bool(_CYRILLIC.search(text)), bool(_LATIN.search(text))
    if has_c and not has_l:
        return "cyr"
    if has_l and not has_c:
        return "lat"
    return "mixed"


class Cluster:
    """A group of site listings believed to be the same physical project."""

    def __init__(self, rec: dict):
        self.records: List[dict] = [rec]
        self.names: List[str] = [rec.get("project_name", "")]

    def matches(self, rec: dict, threshold: float) -> bool:
        name = rec.get("project_name", "")
        best = max(name_similarity(name, ex.get("project_name", "")) for ex in self.records)
        if best < threshold:
            return False
        # Strong name match — block only on a *clear, same-script* developer conflict
        # (cross-script names like "Планекс" vs "Planex" are not comparable here).
        dev = (rec.get("developer_name") or "").strip().lower()
        if dev:
            for existing in self.records:
                ex_dev = (existing.get("developer_name") or "").strip().lower()
                if ex_dev and _script(dev) == _script(ex_dev) != "mixed" \
                        and name_similarity(dev, ex_dev) < 0.7:
                    return False
        return True

    def add(self, rec: dict) -> None:
        self.records.append(rec)
        self.names.append(rec.get("project_name", ""))


def _first(records: List[dict], field: str):
    for r in records:
        v = r.get(field)
        if v not in (None, "", [], {}):
            return v
    return None


def _best_price(records: List[dict]) -> Optional[float]:
    prices = [float(r["price_eur_sqm"]) for r in records
              if r.get("price_eur_sqm") not in (None, "", 0)]
    return round(median(prices), 2) if prices else None


def _canonicalize(cluster: Cluster, city: str) -> dict:
    recs = cluster.records
    # canonical name = the longest non-empty name (usually the most descriptive)
    name = max((n for n in cluster.names if n), key=len, default="")
    neighborhood_slug = _first(recs, "neighborhood_slug")
    neighborhood = _first(recs, "neighborhood")
    seen = sorted(r.get("scraped_at", "") for r in recs if r.get("scraped_at"))
    key_basis = f"{city}|{neighborhood_slug or neighborhood or ''}|{'-'.join(sorted(set(_tokens(name))))}"
    return {
        "canonical_key": _slugify(key_basis),
        "city": city,
        "name": name,
        "developer_name": _first(recs, "developer_name"),
        "neighborhood": neighborhood,
        "neighborhood_slug": neighborhood_slug,
        "akt_stage": _first(recs, "akt_stage"),
        "completion_year": _first(recs, "completion_year"),
        "floors": _first(recs, "floors"),
        "materials": _first(recs, "materials"),
        "price_eur_sqm": _best_price(recs),
        "area_min_sqm": _first(recs, "area_min_sqm"),
        "area_max_sqm": _first(recs, "area_max_sqm"),
        "first_seen": (seen[0][:10] if seen else None),
        "last_seen": (seen[-1][:10] if seen else None),
        "sources": [
            {
                "site": r.get("source_site"),
                "source_name": r.get("project_name"),
                "url": r.get("url"),
                "price_eur_sqm": r.get("price_eur_sqm"),
                "scraped_at": r.get("scraped_at"),
            }
            for r in recs
        ],
    }


def normalize_city(city: str, threshold: float = 0.82) -> tuple[int, int]:
    files = sorted(glob.glob(str(DATA_ROOT / "raw" / "new_buildings" / city / "*.jsonl")))
    raw_rows = 0

    # Block by neighbourhood so we only compare plausibly-colocated projects.
    blocks: dict[str, List[Cluster]] = {}
    for path in files:
        for rec in load_jsonl(path):
            raw_rows += 1
            block_key = (rec.get("neighborhood_slug") or rec.get("neighborhood") or "_").lower()
            clusters = blocks.setdefault(block_key, [])
            for cluster in clusters:
                if cluster.matches(rec, threshold):
                    cluster.add(rec)
                    break
            else:
                clusters.append(Cluster(rec))

    out_dir = DATA_ROOT / "normalized" / "new_buildings"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{city}.jsonl"
    canonical = 0
    with out_path.open("w", encoding="utf-8") as fh:
        for clusters in blocks.values():
            for cluster in clusters:
                fh.write(json.dumps(_canonicalize(cluster, city), ensure_ascii=False) + "\n")
                canonical += 1

    return raw_rows, canonical


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--city", required=True)
    parser.add_argument("--threshold", type=float, default=0.82,
                        help="name-similarity merge threshold (0..1)")
    args = parser.parse_args()
    raw_rows, canonical = normalize_city(args.city, args.threshold)
    print(f"new_buildings[{args.city}]: {raw_rows} raw listings -> {canonical} canonical projects")


if __name__ == "__main__":
    main()
