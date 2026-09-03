#!/usr/bin/env python3
"""
Sofia Neighbourhood Geocoder
=============================
Geocodes all Sofia neighbourhoods via Nominatim (OSM) and saves results
to data/raw/transport/sofia_neighbourhood_coords.json.

Saves after EVERY request — a .tmp file is written incrementally so
partial results survive any interruption. The final file is only written
after all requests complete successfully (or are attempted).

Usage:
    python3 geocode_neighbourhoods.py
    python3 geocode_neighbourhoods.py --resume   # skip already geocoded slugs
"""

import argparse
import json
import sys
import time
import pathlib

import httpx
from typing import Optional

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# Sofia bounding box: lat 42.60–42.80, lon 23.15–23.52
SOFIA_BBOX = {"lat_min": 42.60, "lat_max": 42.80, "lon_min": 23.15, "lon_max": 23.52}

OUTPUT_PATH = pathlib.Path("data/raw/transport/sofia_neighbourhood_coords.json")
TMP_PATH    = pathlib.Path("data/raw/transport/sofia_neighbourhood_coords.tmp.json")

# Sofia neighbourhoods: (slug, Bulgarian name)
# Slug matches imot.bg URL slugs exactly
SOFIA_NEIGHBOURHOODS = [
    ("lozenets",          "Лозенец"),
    ("mladost-1",         "Младост 1"),
    ("mladost-2",         "Младост 2"),
    ("mladost-3",         "Младост 3"),
    ("mladost-4",         "Младост 4"),
    ("vitosha",           "Витоша"),
    ("manastirski-livadi","Манастирски ливади"),
    ("studentski-grad",   "Студентски град"),
    ("lyulin-tsentar",    "Люлин - Център"),
    ("lyulin-1",          "Люлин 1"),
    ("lyulin-2",          "Люлин 2"),
    ("lyulin-3",          "Люлин 3"),
    ("lyulin-4",          "Люлин 4"),
    ("lyulin-5",          "Люлин 5"),
    ("lyulin-6",          "Люлин 6"),
    ("lyulin-7",          "Люлин 7"),
    ("lyulin-8",          "Люлин 8"),
    ("lyulin-9",          "Люлин 9"),
    ("lyulin-10",         "Люлин 10"),
    ("borovo",            "Борово"),
    ("boyana",            "Бояна"),
    ("dragalevtsi",       "Драгалевци"),
    ("simeonovo",         "Симеоново"),
    ("krastova-vada",     "Кръстова вада"),
    ("iztok",             "Изток"),
    ("izgrev",            "Изгрев"),
    ("ivan-vazov",        "Иван Вазов"),
    ("oborishte",         "Оборище"),
    ("tsentar",           "Център"),
    ("yavorov",           "Яворов"),
    ("geo-milev",         "Гео Милев"),
    ("gotse-delchev",     "Гоце Делчев"),
    ("musagenitsa",       "Мусагеница"),
    ("strelbishte",       "Стрелбище"),
    ("krasno-selo",       "Красно село"),
    ("hipodruma",         "Хиподрума"),
    ("hladilnika",        "Хладилника"),
    ("lagera",            "Лагера"),
    ("banishora",         "Банишора"),
    ("slatina",           "Слатина"),
    ("druzhba-1",         "Дружба 1"),
    ("druzhba-2",         "Дружба 2"),
    ("darvenitsa",        "Дървеница"),
    ("nadezhda-1",        "Надежда 1"),
    ("nadezhda-2",        "Надежда 2"),
    ("nadezhda-3",        "Надежда 3"),
    ("nadezhda-4",        "Надежда 4"),
    ("ovcha-kupel",       "Овча купел"),
    ("ovcha-kupel-1",     "Овча купел 1"),
    ("ovcha-kupel-2",     "Овча купел 2"),
    ("belite-brezi",      "Белите брези"),
    ("malinova-dolina",   "Малинова долина"),
    ("gorublyane",        "Горубляне"),
    ("dianabad",          "Дианабад"),
    ("reduta",            "Редута"),
    ("pavlovo",           "Павлово"),
    ("knyazhevo",         "Княжево"),
    ("gorna-banya",       "Горна баня"),
    ("levski",            "Левски"),
    ("zapaden-park",      "Западен парк"),
    ("svoboda",           "Свобода"),
    ("poduyane",          "Подуяне"),
]


def in_sofia_bbox(lat: float, lon: float) -> bool:
    return (
        SOFIA_BBOX["lat_min"] <= lat <= SOFIA_BBOX["lat_max"]
        and SOFIA_BBOX["lon_min"] <= lon <= SOFIA_BBOX["lon_max"]
    )


def geocode(name_bg: str, client: httpx.Client) -> Optional[tuple[float, float]]:
    """Return (lat, lon) from Nominatim or None on failure."""
    try:
        resp = client.get(
            NOMINATIM_URL,
            params={
                "q": f"{name_bg}, София, България",
                "format": "json",
                "limit": 1,
                "countrycodes": "bg",
            },
            headers={"User-Agent": "bg-realestate-intel/1.0 (research geocoding)"},
            timeout=15,
        )
        resp.raise_for_status()
        results = resp.json()
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception as e:
        print(f"    ⚠ Error: {e}", file=sys.stderr)
    return None


def save_tmp(results: dict) -> None:
    """Overwrite the .tmp file with current results after every request."""
    TMP_PATH.parent.mkdir(parents=True, exist_ok=True)
    TMP_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Geocode Sofia neighbourhoods via Nominatim")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip slugs already present in the .tmp file (useful after interruption)",
    )
    args = parser.parse_args()

    # Load existing partial results if resuming
    results: dict = {}
    if args.resume and TMP_PATH.exists():
        results = json.loads(TMP_PATH.read_text(encoding="utf-8"))
        print(f"Resuming — {len(results)} slugs already done.", file=sys.stderr)

    total = len(SOFIA_NEIGHBOURHOODS)
    todo = [
        (slug, name)
        for slug, name in SOFIA_NEIGHBOURHOODS
        if not args.resume or slug not in results
    ]
    print(f"Geocoding {len(todo)}/{total} neighbourhoods (Nominatim, 1 req/sec)...\n",
          file=sys.stderr)

    with httpx.Client(follow_redirects=True) as client:
        for i, (slug, name_bg) in enumerate(todo, 1):
            done_total = len(results)
            print(f"  [{done_total + 1}/{total}] {name_bg} ({slug})...",
                  file=sys.stderr, end=" ", flush=True)

            coords = geocode(name_bg, client)

            if coords is None:
                results[slug] = {
                    "name": name_bg,
                    "lat": None,
                    "lon": None,
                    "status": "geocode_failed",
                    "in_sofia_bbox": False,
                }
                print("✗ not found", file=sys.stderr)
            else:
                lat, lon = coords
                in_bbox = in_sofia_bbox(lat, lon)
                results[slug] = {
                    "name": name_bg,
                    "lat": lat,
                    "lon": lon,
                    "status": "ok" if in_bbox else "outside_sofia_bbox",
                    "in_sofia_bbox": in_bbox,
                }
                flag = "✓" if in_bbox else "⚠ OUTSIDE BBOX"
                print(f"{flag}  ({lat:.4f}, {lon:.4f})", file=sys.stderr)

            # Save after EVERY request — never lose progress
            save_tmp(results)

            if i < len(todo):
                time.sleep(1.1)  # Nominatim rate limit: max 1 req/sec

    # --- Summary ---
    ok      = [s for s, v in results.items() if v["status"] == "ok"]
    outside = [s for s, v in results.items() if v["status"] == "outside_sofia_bbox"]
    failed  = [s for s, v in results.items() if v["status"] == "geocode_failed"]

    print(f"\n{'='*50}", file=sys.stderr)
    print(f"Results: {len(ok)} valid | {len(outside)} outside bbox | {len(failed)} failed",
          file=sys.stderr)
    if outside:
        print(f"Outside bbox (need manual review): {outside}", file=sys.stderr)
    if failed:
        print(f"Failed: {failed}", file=sys.stderr)

    # Write final file (identical content to .tmp, but at the canonical path)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ Saved → {OUTPUT_PATH}", file=sys.stderr)
    print(f"   Temp file kept at {TMP_PATH} (safe to delete)", file=sys.stderr)


if __name__ == "__main__":
    main()
