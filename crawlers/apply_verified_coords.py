#!/usr/bin/env python3
"""
Merge verification results into a clean corrected coords file.

Rules:
- If bounded result exists → use it (stricter Nominatim with Sofia viewbox)
- If bounded result is identical for multiple sub-district siblings → flag as centroid_only
  (e.g. Люлин 1–10 all returning the same point — Nominatim doesn't know sub-districts)
- Final file: sofia_neighbourhood_coords_corrected.json
"""

import json
import pathlib
from collections import defaultdict

VERIFIED   = pathlib.Path("data/raw/transport/sofia_coords_verified.json")
OUTPUT     = pathlib.Path("data/raw/transport/sofia_neighbourhood_coords_corrected.json")

data = json.loads(VERIFIED.read_text(encoding="utf-8"))

# Detect slugs where multiple entries share the exact same bounded coordinate
# → Nominatim returned the parent-district centroid, not the actual sub-district
bounded_coord_to_slugs: dict[tuple, list[str]] = defaultdict(list)
for slug, v in data.items():
    blat = v.get("bounded_lat")
    blon = v.get("bounded_lon")
    if blat is not None:
        bounded_coord_to_slugs[(round(blat, 4), round(blon, 4))].append(slug)

centroid_only_slugs: set[str] = set()
for coord, slugs in bounded_coord_to_slugs.items():
    if len(slugs) > 1:
        centroid_only_slugs.update(slugs)

result = {}
for slug, v in data.items():
    blat = v.get("bounded_lat")
    blon = v.get("bounded_lon")
    stored_lat = v.get("stored_lat")
    stored_lon = v.get("stored_lon")
    stored_ok  = v.get("stored_status") == "ok"

    is_centroid_only = slug in centroid_only_slugs

    if blat is not None and not is_centroid_only:
        final_lat, final_lon = blat, blon
        source = "nominatim_bounded"
    elif stored_ok:
        final_lat, final_lon = stored_lat, stored_lon
        source = "nominatim_stored"
    else:
        final_lat, final_lon = blat, blon   # best we have even if centroid
        source = "nominatim_centroid_only"

    needs_manual = is_centroid_only or (blat is None and not stored_ok)

    result[slug] = {
        "name": v["name"],
        "lat": final_lat,
        "lon": final_lon,
        "source": source,
        "needs_manual_review": needs_manual,
        "note": (
            "Multiple sub-districts resolve to same centroid — Nominatim has no precise data for numbered sub-districts"
            if is_centroid_only else
            ("Corrected: was outside Sofia bbox" if v.get("stored_status") == "outside_sofia_bbox" else None)
        ),
    }

OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

# Print report
total = len(result)
ok    = sum(1 for v in result.values() if not v["needs_manual_review"])
manual = sum(1 for v in result.values() if v["needs_manual_review"])
centroid_groups = {
    coord: slugs for coord, slugs in bounded_coord_to_slugs.items() if len(slugs) > 1
}

print(f"\n{'='*60}")
print(f"Total: {total}  |  Clean: {ok}  |  Needs manual: {manual}")
print(f"\nNeeds manual review ({manual} slugs):")
for slug, v in result.items():
    if v["needs_manual_review"]:
        print(f"  {slug:25s}  ({v['lat']:.4f}, {v['lon']:.4f})  ← {v['source']}")
        if v.get("note"):
            print(f"  {'':25s}  note: {v['note'][:80]}")

print(f"\nCentroid-only groups (multiple slugs → same point):")
for coord, slugs in centroid_groups.items():
    print(f"  {coord} → {slugs}")

print(f"\n✅ Saved → {OUTPUT}")
