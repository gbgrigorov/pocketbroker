#!/usr/bin/env python3
"""
Verify Sofia neighbourhood coordinates.

For each neighbourhood:
1. Re-queries Nominatim with viewbox=Sofia + bounded=1 (stricter)
2. Reverse-geocodes the stored coordinate to confirm what's actually there
3. Computes distance between stored vs bounded result
4. Flags any large discrepancies

Saves: data/raw/transport/sofia_coords_verified.json
       data/raw/transport/sofia_coords_verified.tmp.json  (incremental)
"""

import json
import sys
import time
import math
import pathlib
from typing import Optional

import httpx

NOMINATIM_URL  = "https://nominatim.openstreetmap.org/search"
REVERSE_URL    = "https://nominatim.openstreetmap.org/reverse"

SOFIA_BBOX     = (42.60, 23.15, 42.80, 23.52)   # S, W, N, E
VIEWBOX        = f"{SOFIA_BBOX[1]},{SOFIA_BBOX[0]},{SOFIA_BBOX[3]},{SOFIA_BBOX[2]}"  # W,S,E,N for Nominatim

EXISTING_FILE  = pathlib.Path("data/raw/transport/sofia_neighbourhood_coords.json")
OUTPUT_FILE    = pathlib.Path("data/raw/transport/sofia_coords_verified.json")
TMP_FILE       = pathlib.Path("data/raw/transport/sofia_coords_verified.tmp.json")

HEADERS = {"User-Agent": "bg-realestate-intel/1.0 (coord-verification)"}

DIST_WARN_M = 2000   # flag if bounded result is >2km from stored coord


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    R = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def in_bbox(lat, lon) -> bool:
    return SOFIA_BBOX[0] <= lat <= SOFIA_BBOX[2] and SOFIA_BBOX[1] <= lon <= SOFIA_BBOX[3]


def forward_bounded(name_bg: str, client: httpx.Client) -> Optional[dict]:
    """Nominatim forward search with viewbox+bounded — forces results inside Sofia."""
    try:
        resp = client.get(NOMINATIM_URL, params={
            "q": f"{name_bg}, София, България",
            "format": "json",
            "limit": 3,
            "countrycodes": "bg",
            "viewbox": VIEWBOX,
            "bounded": "1",
        }, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        results = resp.json()
        if results:
            best = results[0]
            return {
                "lat": float(best["lat"]),
                "lon": float(best["lon"]),
                "display_name": best.get("display_name", ""),
                "osm_type": best.get("osm_type", ""),
                "osm_id": best.get("osm_id"),
                "type": best.get("type", ""),
                "class": best.get("class", ""),
            }
    except Exception as e:
        print(f"    forward_bounded error: {e}", file=sys.stderr)
    return None


def reverse_geocode(lat: float, lon: float, client: httpx.Client) -> Optional[str]:
    """Return display_name for a lat/lon."""
    try:
        resp = client.get(REVERSE_URL, params={
            "lat": lat, "lon": lon,
            "format": "json",
            "zoom": 14,        # neighbourhood level
        }, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("display_name", "")
    except Exception as e:
        print(f"    reverse error: {e}", file=sys.stderr)
    return None


def save_tmp(results: dict) -> None:
    TMP_FILE.parent.mkdir(parents=True, exist_ok=True)
    TMP_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    existing = json.loads(EXISTING_FILE.read_text(encoding="utf-8"))
    results: dict = {}

    slugs = list(existing.keys())
    total = len(slugs)
    print(f"Verifying {total} neighbourhoods (2 Nominatim calls each = ~{total*2*1.2:.0f}s)\n",
          file=sys.stderr)

    with httpx.Client(follow_redirects=True) as client:
        for i, slug in enumerate(slugs, 1):
            stored = existing[slug]
            name_bg = stored["name"]
            stored_lat = stored.get("lat")
            stored_lon = stored.get("lon")

            print(f"[{i:02d}/{total}] {name_bg} ({slug})", file=sys.stderr)

            # --- Step A: forward search with bounded viewbox ---
            time.sleep(1.1)
            bounded = forward_bounded(name_bg, client)

            # --- Step B: reverse-geocode the stored coordinate ---
            reverse_label = None
            if stored_lat is not None:
                time.sleep(1.1)
                reverse_label = reverse_geocode(stored_lat, stored_lon, client)

            # --- Evaluate ---
            issues = []

            if stored.get("status") == "outside_sofia_bbox":
                issues.append("stored_outside_bbox")

            bounded_lat = bounded["lat"] if bounded else None
            bounded_lon = bounded["lon"] if bounded else None

            dist_m = None
            if stored_lat and bounded_lat:
                dist_m = haversine_m(stored_lat, stored_lon, bounded_lat, bounded_lon)
                if dist_m > DIST_WARN_M:
                    issues.append(f"large_shift_{int(dist_m)}m")

            if bounded is None:
                issues.append("no_bounded_result")

            # What does the reverse label say?
            reverse_ok = None
            if reverse_label:
                # Check if the Bulgarian name appears (roughly) in the reverse result
                name_simple = name_bg.replace(" - ", " ").lower()
                reverse_ok = any(
                    part in reverse_label.lower()
                    for part in name_simple.split()
                    if len(part) > 3
                )

            status = "ok" if not issues else "review"

            rec = {
                "name": name_bg,
                "stored_lat": stored_lat,
                "stored_lon": stored_lon,
                "stored_status": stored.get("status"),
                "bounded_lat": bounded_lat,
                "bounded_lon": bounded_lon,
                "bounded_display": bounded["display_name"] if bounded else None,
                "bounded_osm_type": bounded["osm_type"] if bounded else None,
                "dist_stored_vs_bounded_m": round(dist_m) if dist_m is not None else None,
                "reverse_label": reverse_label,
                "reverse_name_match": reverse_ok,
                "issues": issues,
                "verification_status": status,
                # Final recommended coords
                "recommended_lat": bounded_lat if bounded_lat else stored_lat,
                "recommended_lon": bounded_lon if bounded_lon else stored_lon,
                "recommended_source": "bounded" if bounded_lat else "stored",
            }
            results[slug] = rec

            # Print one-line verdict
            verdict = "✅" if status == "ok" else "⚠️ "
            dist_str = f"  Δ{int(dist_m)}m" if dist_m and dist_m > 100 else ""
            rev_str = f"  rev={'✓' if reverse_ok else '✗'}" if reverse_ok is not None else ""
            print(f"     {verdict} {status.upper()}{dist_str}{rev_str}", file=sys.stderr)
            if bounded:
                print(f"     bounded  → ({bounded_lat:.4f}, {bounded_lon:.4f})", file=sys.stderr)
            if issues:
                print(f"     issues   → {issues}", file=sys.stderr)

            save_tmp(results)

    # Final save
    OUTPUT_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    # Summary
    ok_count     = sum(1 for v in results.values() if v["verification_status"] == "ok")
    review_count = sum(1 for v in results.values() if v["verification_status"] == "review")
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"✅ {ok_count} ok   ⚠️  {review_count} need review", file=sys.stderr)
    review_slugs = [s for s, v in results.items() if v["verification_status"] == "review"]
    if review_slugs:
        print(f"Review: {review_slugs}", file=sys.stderr)
    print(f"\nSaved → {OUTPUT_FILE}", file=sys.stderr)


if __name__ == "__main__":
    main()
