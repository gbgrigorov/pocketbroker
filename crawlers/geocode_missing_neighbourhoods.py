#!/usr/bin/env python3
"""
Geocode the MISSING Sofia neighbourhoods
========================================
Companion to ``geocode_neighbourhoods.py``. That script geocoded the original 62
mapped neighbourhoods from a hardcoded list. This one fills the gap: every
neighbourhood that has a price record (and therefore an imot.bg slug) but is NOT
yet present in ``sofia_neighbourhood_coords.json``.

The work list is derived from data, not hardcoded:
    priced slugs (current sale + rent snapshots)  −  slugs already in coords file

Each missing slug is geocoded via Nominatim (OSM), with the query string cleaned
per imot.bg prefix (с. / гр. / в.з. / ж.гр. / м-т / НПЗ / ПЗ / numbered ж.к.).
Results are MERGED non-destructively into the canonical coords file — the existing
entries are never touched — in the canonical schema:

    {"name": ..., "lat": ..., "lon": ..., "source": ..., "verified": bool}

Because the bubble map is a force-packed cluster (approximate positions), any name
Nominatim cannot resolve falls back to the Sofia centroid + a small deterministic
jitter so it still gets a bubble; these are printed explicitly for later review.

Usage:
    python3 crawlers/geocode_missing_neighbourhoods.py
    python3 crawlers/geocode_missing_neighbourhoods.py --resume   # skip done slugs
    python3 crawlers/geocode_missing_neighbourhoods.py --dry-run  # list work, no network
"""

import argparse
import json
import pathlib
import sys
import time
from typing import Optional

import httpx

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CURRENT_SALE = REPO_ROOT / "data/raw/imot_bg/sofia_current_2026-05.jsonl"
CURRENT_RENT = REPO_ROOT / "data/raw/imot_bg/sofia_current_rent_2026-05.jsonl"
COORDS_PATH = REPO_ROOT / "data/raw/transport/sofia_neighbourhood_coords.json"
TMP_PATH = REPO_ROOT / "data/raw/transport/sofia_missing_coords.tmp.json"

# Greater Sofia municipality (Столична община) — wide on purpose so outlying
# villages/towns (Банкя W, Нови Искър N, Панчарево/Лозен/Бистрица SE) are accepted.
GREATER_SOFIA = {"lat_min": 42.45, "lat_max": 42.95, "lon_min": 22.95, "lon_max": 23.75}

# Approximate Sofia city centre — fallback anchor for un-geocodable names.
SOFIA_CENTROID = (42.6977, 23.3219)


def in_greater_sofia(lat: float, lon: float) -> bool:
    return (
        GREATER_SOFIA["lat_min"] <= lat <= GREATER_SOFIA["lat_max"]
        and GREATER_SOFIA["lon_min"] <= lon <= GREATER_SOFIA["lon_max"]
    )


def load_jsonl_names(path: pathlib.Path) -> dict:
    """Return {slug: name} for every priced row that carries a slug."""
    out: dict = {}
    if not path.exists():
        return out
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            slug = rec.get("neighborhood_slug")
            name = (rec.get("neighborhood") or "").strip()
            if slug and name and slug not in out:
                out[slug] = name
    return out


def build_query(name: str) -> str:
    """Clean an imot.bg display name into a Nominatim-friendly query string."""
    n = name.strip()

    # Outlying settlements — let Nominatim place them at their true location.
    if n.startswith("с. ") or n.startswith("с."):
        village = n.split(".", 1)[1].strip()
        return f"{village}, Столична община, България"
    if n.startswith("гр. ") or n.startswith("гр."):
        town = n.split(".", 1)[1].strip()
        return f"{town}, София, България"

    # Prefixed zones/localities — strip the prefix, query the bare name in Sofia.
    for prefix in ("в.з.", "ж.гр.", "м-т ", "м-т", "НПЗ ", "НПЗ", "ПЗ ", "ПЗ"):
        if n.startswith(prefix):
            bare = n[len(prefix):].strip()
            return f"{bare}, София, България"

    # Numbered residential complexes resolve better with the ж.к. framing.
    last = n.split()[-1] if n.split() else ""
    if last.isdigit() or last in {"1А", "1A"}:
        return f"ж.к. {n}, София, България"

    return f"{n}, София, България"


def geocode(query: str, client: httpx.Client, bounded: bool = False) -> Optional[tuple]:
    """Return (lat, lon) from Nominatim or None on failure/no-result.

    When ``bounded`` is set the search is biased/restricted to the greater-Sofia
    viewbox — useful for ambiguous bare names that otherwise match a homonym
    elsewhere in Bulgaria.
    """
    params = {"q": query, "format": "json", "limit": 1, "countrycodes": "bg"}
    if bounded:
        params["viewbox"] = (f"{GREATER_SOFIA['lon_min']},{GREATER_SOFIA['lat_max']},"
                             f"{GREATER_SOFIA['lon_max']},{GREATER_SOFIA['lat_min']}")
        params["bounded"] = 1
    try:
        resp = client.get(
            NOMINATIM_URL,
            params=params,
            headers={"User-Agent": "bg-realestate-intel/1.0 (research geocoding)"},
            timeout=15,
        )
        resp.raise_for_status()
        results = resp.json()
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception as e:  # noqa: BLE001
        print(f"    ⚠ Error: {e}", file=sys.stderr)
    return None


def retry_queries(name: str) -> list:
    """Alternate query strings for a name that failed the first pass."""
    n = name.strip()
    for prefix in ("с. ", "с.", "гр. ", "гр.", "в.з.", "ж.гр.", "м-т ", "м-т",
                   "НПЗ ", "НПЗ", "ПЗ ", "ПЗ"):
        if n.startswith(prefix):
            n = n[len(prefix):].strip()
            break
    base = n.split(" - ")[0].split(",")[0].strip()  # drop "- Герена" / "3 част" tails
    return [
        f"{n}, София",
        f"село {base}, България",
        f"{base}, София",
        base,
    ]


def jittered_centroid(slug: str) -> tuple:
    """Deterministic small offset from the city centre, keyed on the slug."""
    h = abs(hash(slug))
    dlat = ((h % 1000) / 1000.0 - 0.5) * 0.04   # ±0.02° (~2.2 km)
    dlon = (((h // 1000) % 1000) / 1000.0 - 0.5) * 0.06  # ±0.03°
    return (SOFIA_CENTROID[0] + dlat, SOFIA_CENTROID[1] + dlon)


def save_tmp(results: dict) -> None:
    TMP_PATH.parent.mkdir(parents=True, exist_ok=True)
    TMP_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


RETRYABLE = {"fallback_centroid", "nominatim_outside_bbox"}


def retry_failures() -> None:
    """Re-geocode entries that fell back to the centroid or landed outside Sofia."""
    coords = json.loads(COORDS_PATH.read_text(encoding="utf-8"))
    targets = {s: v for s, v in coords.items() if v.get("source") in RETRYABLE}
    print(f"Retrying {len(targets)} unresolved/outside entries (viewbox-bounded)...\n",
          file=sys.stderr)

    fixed, still = 0, []
    with httpx.Client(follow_redirects=True) as client:
        for slug, entry in targets.items():
            name = entry["name"]
            print(f"  {name} ({slug})", file=sys.stderr, end=" ", flush=True)
            hit = None
            for q in retry_queries(name):
                hit = geocode(q, client, bounded=True)
                time.sleep(1.1)
                if hit and in_greater_sofia(*hit):
                    break
                hit = None
            if hit:
                coords[slug] = {"name": name, "lat": hit[0], "lon": hit[1],
                                "source": "nominatim", "verified": True}
                fixed += 1
                print(f"✓ fixed ({hit[0]:.4f}, {hit[1]:.4f})", file=sys.stderr)
            else:
                still.append(slug)
                print("✗ still unresolved (keeping fallback)", file=sys.stderr)

    COORDS_PATH.write_text(json.dumps(coords, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(f"\n{'=' * 56}\nFixed {fixed}/{len(targets)}; {len(still)} still on fallback: "
          f"{still}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Geocode missing Sofia neighbourhoods")
    parser.add_argument("--resume", action="store_true",
                        help="skip slugs already present in the .tmp file")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the work list and queries, make no network calls")
    parser.add_argument("--retry-failures", action="store_true",
                        help="re-geocode existing centroid-fallback / outside-bbox entries "
                             "with alternate viewbox-bounded queries")
    args = parser.parse_args()

    if args.retry_failures:
        retry_failures()
        return

    # Existing coords — the source of truth for what is already mapped.
    coords = json.loads(COORDS_PATH.read_text(encoding="utf-8"))

    # Priced slugs across sale + rent snapshots.
    priced = load_jsonl_names(CURRENT_SALE)
    for slug, name in load_jsonl_names(CURRENT_RENT).items():
        priced.setdefault(slug, name)

    missing = {s: n for s, n in priced.items() if s not in coords}
    missing = dict(sorted(missing.items()))
    print(f"Priced slugs: {len(priced)} | already mapped: {len(coords)} | "
          f"missing: {len(missing)}", file=sys.stderr)

    if args.dry_run:
        for slug, name in missing.items():
            print(f"  {slug:34s} {name:30s} -> {build_query(name)}")
        return

    # Resume from the .tmp staging file if asked.
    results: dict = {}
    if args.resume and TMP_PATH.exists():
        results = json.loads(TMP_PATH.read_text(encoding="utf-8"))
        print(f"Resuming — {len(results)} already geocoded.", file=sys.stderr)

    todo = [(s, n) for s, n in missing.items() if s not in results]
    print(f"Geocoding {len(todo)}/{len(missing)} (Nominatim, 1 req/sec)...\n",
          file=sys.stderr)

    with httpx.Client(follow_redirects=True) as client:
        for i, (slug, name) in enumerate(todo, 1):
            query = build_query(name)
            print(f"  [{len(results) + 1}/{len(missing)}] {name} ({slug})",
                  file=sys.stderr, end=" ", flush=True)
            coord = geocode(query, client)

            if coord is None:
                lat, lon = jittered_centroid(slug)
                results[slug] = {"name": name, "lat": lat, "lon": lon,
                                 "source": "fallback_centroid", "verified": False}
                print("✗ not found → centroid fallback", file=sys.stderr)
            else:
                lat, lon = coord
                inside = in_greater_sofia(lat, lon)
                results[slug] = {
                    "name": name, "lat": lat, "lon": lon,
                    "source": "nominatim" if inside else "nominatim_outside_bbox",
                    "verified": inside,
                }
                flag = "✓" if inside else "⚠ OUTSIDE greater-Sofia"
                print(f"{flag}  ({lat:.4f}, {lon:.4f})", file=sys.stderr)

            save_tmp(results)
            if i < len(todo):
                time.sleep(1.1)  # Nominatim rate limit

    # --- Merge non-destructively into the canonical coords file ---
    overlap = set(results) & set(coords)
    if overlap:
        print(f"\n⚠ Refusing to overwrite {len(overlap)} existing slugs: "
              f"{sorted(overlap)}", file=sys.stderr)
        for s in overlap:
            results.pop(s, None)
    merged = {**coords, **results}
    COORDS_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2),
                           encoding="utf-8")

    # --- Summary ---
    ok = [s for s, v in results.items() if v["source"] == "nominatim"]
    outside = [s for s, v in results.items() if v["source"] == "nominatim_outside_bbox"]
    fallback = [s for s, v in results.items() if v["source"] == "fallback_centroid"]
    print(f"\n{'=' * 56}", file=sys.stderr)
    print(f"Added {len(results)}: {len(ok)} clean | {len(outside)} outside-bbox | "
          f"{len(fallback)} centroid-fallback", file=sys.stderr)
    if outside:
        print(f"\nOutside greater-Sofia bbox (eyeball these):", file=sys.stderr)
        for s in outside:
            print(f"   {s:34s} ({results[s]['lat']:.4f}, {results[s]['lon']:.4f})  "
                  f"{results[s]['name']}", file=sys.stderr)
    if fallback:
        print(f"\nNot found → centroid fallback (refine later):", file=sys.stderr)
        for s in fallback:
            print(f"   {s:34s} {results[s]['name']}", file=sys.stderr)
    print(f"\n✅ Coords file now has {len(merged)} entries → {COORDS_PATH}",
          file=sys.stderr)
    print(f"   Staging file kept at {TMP_PATH} (safe to delete)", file=sys.stderr)


if __name__ == "__main__":
    main()
