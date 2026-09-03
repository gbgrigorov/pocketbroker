#!/usr/bin/env python3
"""
Geocode a city's imot.bg neighbourhoods (Varna / Burgas / Plovdiv / Sofia)
==========================================================================
City-parametrized generalization of ``geocode_missing_neighbourhoods.py`` (which
is Sofia-specific). The work list is derived from data, not hardcoded:

    priced slugs (current sale + rent snapshots)  −  slugs already in the city
                                                     coords file

Each slug is geocoded via Nominatim (OSM). Queries are framed with the city's
Bulgarian name (``"{name}, Варна, България"``) and imot.bg prefixes are cleaned
(с. / гр. / в.з. / ж.гр. / м-т / НПЗ / ПЗ / numbered ж.к.). Results are merged
non-destructively into ``data/raw/transport/{city}_neighbourhood_coords.json`` in
the canonical schema:

    {"name": ..., "lat": ..., "lon": ..., "source": ..., "verified": bool}

Any name Nominatim cannot resolve (or that lands outside the city bbox) falls back
to the city centroid + a small deterministic jitter so it still gets a bubble;
these are printed for later review.

Usage:
    python3 crawlers/geocode_city_neighbourhoods.py --city varna
    python3 crawlers/geocode_city_neighbourhoods.py --city burgas --resume
    python3 crawlers/geocode_city_neighbourhoods.py --city plovdiv --dry-run
    python3 crawlers/geocode_city_neighbourhoods.py --city varna --retry-failures
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
RAW = REPO_ROOT / "data/raw/imot_bg"
TRANSPORT = REPO_ROOT / "data/raw/transport"

# Per-city config: Bulgarian name (for the query), centroid (centroid fallback),
# and a generous bounding box used to sanity-check Nominatim hits.
CITIES = {
    "varna": {
        "name": "Варна",
        "centroid": (43.2046, 27.9106),
        "bbox": {"lat_min": 43.10, "lat_max": 43.30, "lon_min": 27.78, "lon_max": 28.05},
    },
    "burgas": {
        "name": "Бургас",
        "centroid": (42.5048, 27.4626),
        "bbox": {"lat_min": 42.40, "lat_max": 42.62, "lon_min": 27.35, "lon_max": 27.60},
    },
    "plovdiv": {
        "name": "Пловдив",
        "centroid": (42.1421, 24.7499),
        "bbox": {"lat_min": 42.06, "lat_max": 42.24, "lon_min": 24.62, "lon_max": 24.88},
    },
}


def current_sale_path(city: str) -> pathlib.Path:
    """Newest current sale snapshot for a city (e.g. varna_current_2026-06.jsonl)."""
    files = sorted(RAW.glob(f"{city}_current_2*.jsonl"))
    files = [f for f in files if "_rent_" not in f.name]
    return files[-1] if files else RAW / f"{city}_current.jsonl"


def current_rent_path(city: str) -> pathlib.Path:
    files = sorted(RAW.glob(f"{city}_current_rent_*.jsonl"))
    return files[-1] if files else RAW / f"{city}_current_rent.jsonl"


def coords_path(city: str) -> pathlib.Path:
    return TRANSPORT / f"{city}_neighbourhood_coords.json"


def tmp_path(city: str) -> pathlib.Path:
    return TRANSPORT / f"{city}_coords.tmp.json"


def in_bbox(bbox: dict, lat: float, lon: float) -> bool:
    return (bbox["lat_min"] <= lat <= bbox["lat_max"]
            and bbox["lon_min"] <= lon <= bbox["lon_max"])


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


def build_query(name: str, city_name: str) -> str:
    """Clean an imot.bg display name into a Nominatim-friendly query string."""
    n = name.strip()

    # Outlying settlements — let Nominatim place them at their true location.
    if n.startswith("с. ") or n.startswith("с."):
        village = n.split(".", 1)[1].strip()
        return f"{village}, България"
    if n.startswith("гр. ") or n.startswith("гр."):
        town = n.split(".", 1)[1].strip()
        return f"{town}, България"

    # Prefixed zones/localities — strip the prefix, query the bare name in the city.
    for prefix in ("в.з.", "ж.гр.", "м-т ", "м-т", "НПЗ ", "НПЗ", "ПЗ ", "ПЗ"):
        if n.startswith(prefix):
            bare = n[len(prefix):].strip()
            return f"{bare}, {city_name}, България"

    # Numbered residential complexes resolve better with the ж.к. framing.
    last = n.split()[-1] if n.split() else ""
    if last.isdigit() or last in {"1А", "1A"}:
        return f"ж.к. {n}, {city_name}, България"

    return f"{n}, {city_name}, България"


def retry_queries(name: str, city_name: str) -> list:
    """Alternate query strings for a name that failed the first pass."""
    n = name.strip()
    for prefix in ("с. ", "с.", "гр. ", "гр.", "в.з.", "ж.гр.", "м-т ", "м-т",
                   "НПЗ ", "НПЗ", "ПЗ ", "ПЗ"):
        if n.startswith(prefix):
            n = n[len(prefix):].strip()
            break
    base = n.split(" - ")[0].split(",")[0].strip()  # drop "- Герена" / "3 част" tails
    return [
        f"{n}, {city_name}",
        f"квартал {base}, {city_name}, България",
        f"{base}, {city_name}",
        base,
    ]


def geocode(query: str, client: httpx.Client, bbox: Optional[dict] = None) -> Optional[tuple]:
    """Return (lat, lon) from Nominatim or None. When ``bbox`` given, bound the search."""
    params = {"q": query, "format": "json", "limit": 1, "countrycodes": "bg"}
    if bbox is not None:
        params["viewbox"] = (f"{bbox['lon_min']},{bbox['lat_max']},"
                             f"{bbox['lon_max']},{bbox['lat_min']}")
        params["bounded"] = 1
    try:
        resp = client.get(
            NOMINATIM_URL, params=params,
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


def jittered_centroid(slug: str, centroid: tuple) -> tuple:
    """Deterministic small offset from the city centre, keyed on the slug."""
    h = abs(hash(slug))
    dlat = ((h % 1000) / 1000.0 - 0.5) * 0.04   # ±0.02° (~2.2 km)
    dlon = (((h // 1000) % 1000) / 1000.0 - 0.5) * 0.06  # ±0.03°
    return (centroid[0] + dlat, centroid[1] + dlon)


RETRYABLE = {"fallback_centroid", "nominatim_outside_bbox"}


def retry_failures(city: str) -> None:
    """Re-geocode entries that fell back to the centroid or landed outside the bbox."""
    cfg = CITIES[city]
    cpath = coords_path(city)
    coords = json.loads(cpath.read_text(encoding="utf-8"))
    targets = {s: v for s, v in coords.items() if v.get("source") in RETRYABLE}
    print(f"[{city}] Retrying {len(targets)} unresolved/outside entries (bbox-bounded)...\n",
          file=sys.stderr)

    fixed, still = 0, []
    with httpx.Client(follow_redirects=True) as client:
        for slug, entry in targets.items():
            name = entry["name"]
            print(f"  {name} ({slug})", file=sys.stderr, end=" ", flush=True)
            hit = None
            for q in retry_queries(name, cfg["name"]):
                hit = geocode(q, client, bbox=cfg["bbox"])
                time.sleep(1.1)
                if hit and in_bbox(cfg["bbox"], *hit):
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

    cpath.write_text(json.dumps(coords, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{'=' * 56}\nFixed {fixed}/{len(targets)}; {len(still)} still on fallback: "
          f"{still}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Geocode a city's imot.bg neighbourhoods")
    parser.add_argument("--city", choices=list(CITIES), required=True)
    parser.add_argument("--resume", action="store_true",
                        help="skip slugs already present in the .tmp file")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the work list and queries, make no network calls")
    parser.add_argument("--retry-failures", action="store_true",
                        help="re-geocode existing centroid-fallback / outside-bbox entries")
    args = parser.parse_args()
    city = args.city
    cfg = CITIES[city]

    if args.retry_failures:
        retry_failures(city)
        return

    cpath = coords_path(city)
    coords = json.loads(cpath.read_text(encoding="utf-8")) if cpath.exists() else {}

    # Priced slugs across sale + rent snapshots.
    priced = load_jsonl_names(current_sale_path(city))
    for slug, name in load_jsonl_names(current_rent_path(city)).items():
        priced.setdefault(slug, name)

    missing = dict(sorted((s, n) for s, n in priced.items() if s not in coords))
    print(f"[{city}] Priced slugs: {len(priced)} | already mapped: {len(coords)} | "
          f"missing: {len(missing)}", file=sys.stderr)

    if args.dry_run:
        for slug, name in missing.items():
            print(f"  {slug:34s} {name:30s} -> {build_query(name, cfg['name'])}")
        return

    tpath = tmp_path(city)
    results: dict = {}
    if args.resume and tpath.exists():
        results = json.loads(tpath.read_text(encoding="utf-8"))
        print(f"[{city}] Resuming — {len(results)} already geocoded.", file=sys.stderr)

    todo = [(s, n) for s, n in missing.items() if s not in results]
    print(f"[{city}] Geocoding {len(todo)}/{len(missing)} (Nominatim, 1 req/sec)...\n",
          file=sys.stderr)

    with httpx.Client(follow_redirects=True) as client:
        for i, (slug, name) in enumerate(todo, 1):
            query = build_query(name, cfg["name"])
            print(f"  [{len(results) + 1}/{len(missing)}] {name} ({slug})",
                  file=sys.stderr, end=" ", flush=True)
            coord = geocode(query, client)

            if coord is None:
                lat, lon = jittered_centroid(slug, cfg["centroid"])
                results[slug] = {"name": name, "lat": lat, "lon": lon,
                                 "source": "fallback_centroid", "verified": False}
                print("✗ not found → centroid fallback", file=sys.stderr)
            else:
                lat, lon = coord
                inside = in_bbox(cfg["bbox"], lat, lon)
                results[slug] = {
                    "name": name, "lat": lat, "lon": lon,
                    "source": "nominatim" if inside else "nominatim_outside_bbox",
                    "verified": inside,
                }
                flag = "✓" if inside else f"⚠ OUTSIDE {city} bbox"
                print(f"{flag}  ({lat:.4f}, {lon:.4f})", file=sys.stderr)

            tpath.parent.mkdir(parents=True, exist_ok=True)
            tpath.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            if i < len(todo):
                time.sleep(1.1)  # Nominatim rate limit

    # --- Merge non-destructively into the canonical city coords file ---
    overlap = set(results) & set(coords)
    for s in overlap:
        results.pop(s, None)
    merged = {**coords, **results}
    cpath.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- Summary ---
    ok = [s for s, v in results.items() if v["source"] == "nominatim"]
    outside = [s for s, v in results.items() if v["source"] == "nominatim_outside_bbox"]
    fallback = [s for s, v in results.items() if v["source"] == "fallback_centroid"]
    print(f"\n{'=' * 56}", file=sys.stderr)
    print(f"[{city}] Added {len(results)}: {len(ok)} clean | {len(outside)} outside-bbox | "
          f"{len(fallback)} centroid-fallback", file=sys.stderr)
    if outside:
        print("\nOutside bbox (eyeball these):", file=sys.stderr)
        for s in outside:
            print(f"   {s:34s} ({results[s]['lat']:.4f}, {results[s]['lon']:.4f})  "
                  f"{results[s]['name']}", file=sys.stderr)
    if fallback:
        print("\nNot found → centroid fallback (refine later):", file=sys.stderr)
        for s in fallback:
            print(f"   {s:34s} {results[s]['name']}", file=sys.stderr)
    print(f"\n✅ {city} coords file now has {len(merged)} entries → {cpath}", file=sys.stderr)


if __name__ == "__main__":
    main()
