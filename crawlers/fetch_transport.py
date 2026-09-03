#!/usr/bin/env python3
"""
Sofia Public Transport Fetcher
================================
Fetches metro, tram, and major bus route data for Sofia from OpenStreetMap
via the Overpass API (free, no API key needed).

Maps each route's stops to Sofia neighbourhoods by geocoding neighbourhood
centers via Nominatim and finding stops within proximity thresholds.

Output: data/raw/transport/sofia_transport.json

Usage:
    python3 fetch_transport.py
    python3 fetch_transport.py --output data/raw/transport/sofia_transport.json
    python3 fetch_transport.py --min-bus-stops 8   # filter minor bus routes
"""

import argparse
import json
import math
import sys
import time
from typing import Optional
import pathlib

import httpx

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# Sofia bounding box: south, west, north, east
SOFIA_BBOX = (42.60, 23.15, 42.80, 23.52)

# Proximity thresholds for assigning stops to neighbourhoods
METRO_RADIUS_M = 1200   # metro — larger catchment (people walk further for metro)
TRAM_RADIUS_M = 600
BUS_RADIUS_M = 500

# Sofia neighbourhoods: (slug, Bulgarian name)
# Slug matches imot.bg URL slugs exactly
SOFIA_NEIGHBOURHOODS = [
    ("lozenets",         "Лозенец"),
    ("mladost-1",        "Младост 1"),
    ("mladost-2",        "Младост 2"),
    ("mladost-3",        "Младост 3"),
    ("mladost-4",        "Младост 4"),
    ("vitosha",          "Витоша"),
    ("manastirski-livadi", "Манастирски ливади"),
    ("studentski-grad",  "Студентски град"),
    ("lyulin-tsentar",   "Люлин - Център"),
    ("lyulin-1",         "Люлин 1"),
    ("lyulin-2",         "Люлин 2"),
    ("lyulin-3",         "Люлин 3"),
    ("lyulin-4",         "Люлин 4"),
    ("lyulin-5",         "Люлин 5"),
    ("lyulin-6",         "Люлин 6"),
    ("lyulin-7",         "Люлин 7"),
    ("lyulin-8",         "Люлин 8"),
    ("lyulin-9",         "Люлин 9"),
    ("lyulin-10",        "Люлин 10"),
    ("borovo",           "Борово"),
    ("boyana",           "Бояна"),
    ("dragalevtsi",      "Драгалевци"),
    ("simeonovo",        "Симеоново"),
    ("krastova-vada",    "Кръстова вада"),
    ("iztok",            "Изток"),
    ("izgrev",           "Изгрев"),
    ("ivan-vazov",       "Иван Вазов"),
    ("oborishte",        "Оборище"),
    ("tsentar",          "Център"),
    ("yavorov",          "Яворов"),
    ("geo-milev",        "Гео Милев"),
    ("gotse-delchev",    "Гоце Делчев"),
    ("musagenitsa",      "Мусагеница"),
    ("strelbishte",      "Стрелбище"),
    ("krasno-selo",      "Красно село"),
    ("hipodruma",        "Хиподрума"),
    ("hladilnika",       "Хладилника"),
    ("lagera",           "Лагера"),
    ("banishora",        "Банишора"),
    ("slatina",          "Слатина"),
    ("druzhba-1",        "Дружба 1"),
    ("druzhba-2",        "Дружба 2"),
    ("darvenitsa",       "Дървеница"),
    ("nadezhda-1",       "Надежда 1"),
    ("nadezhda-2",       "Надежда 2"),
    ("nadezhda-3",       "Надежда 3"),
    ("nadezhda-4",       "Надежда 4"),
    ("ovcha-kupel",      "Овча купел"),
    ("ovcha-kupel-1",    "Овча купел 1"),
    ("ovcha-kupel-2",    "Овча купел 2"),
    ("belite-brezi",     "Белите брези"),
    ("malinova-dolina",  "Малинова долина"),
    ("gorublyane",       "Горубляне"),
    ("dianabad",         "Дианабад"),
    ("reduta",           "Редута"),
    ("pavlovo",          "Павлово"),
    ("knyazhevo",        "Княжево"),
    ("gorna-banya",      "Горна баня"),
    ("levski",           "Левски"),
    ("zapaden-park",     "Западен парк"),
    ("svoboda",          "Свобода"),
    ("poduyane",         "Подуяне"),
]


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in metres between two WGS84 lat/lon points."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Overpass queries
# ---------------------------------------------------------------------------

def overpass_query(query: str, client: httpx.Client, retries: int = 3) -> Optional[dict]:
    """Run an Overpass QL query and return parsed JSON."""
    for attempt in range(1, retries + 1):
        try:
            resp = client.post(OVERPASS_URL, data={"data": query}, timeout=60)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"  Overpass error (attempt {attempt}/{retries}): {e}", file=sys.stderr)
            if attempt < retries:
                time.sleep(3 * attempt)
    return None


def fetch_metro_routes(client: httpx.Client) -> dict[str, list[dict]]:
    """
    Returns: {line_ref: [{"name": str, "lat": float, "lon": float}, ...]}
    line_ref is e.g. "M1", "M2", "M3".
    """
    bbox = f"{SOFIA_BBOX[0]},{SOFIA_BBOX[1]},{SOFIA_BBOX[2]},{SOFIA_BBOX[3]}"
    query = f"""
[out:json];
relation["route"="subway"]({bbox});
out body;
>;
out skel qt;
"""
    print("  Fetching metro routes from Overpass...", file=sys.stderr)
    data = overpass_query(query, client)
    if not data:
        return {}

    # Build node id → coordinates lookup
    nodes: dict[int, tuple[float, float]] = {}
    for elem in data.get("elements", []):
        if elem["type"] == "node" and "lat" in elem:
            nodes[elem["id"]] = (elem["lat"], elem["lon"])

    # Extract route relations
    routes: dict[str, list[dict]] = {}
    for elem in data.get("elements", []):
        if elem["type"] != "relation":
            continue
        tags = elem.get("tags", {})
        line_ref = tags.get("ref", tags.get("name", "unknown"))
        # Collect stop members
        stops = []
        for member in elem.get("members", []):
            if member["type"] == "node" and member.get("role") in ("stop", "stop_entry_only", "stop_exit_only", "platform", ""):
                node_id = member["ref"]
                if node_id in nodes:
                    lat, lon = nodes[node_id]
                    # Get stop name from node tags if available
                    stop_name = None
                    for node_elem in data.get("elements", []):
                        if node_elem["type"] == "node" and node_elem["id"] == node_id:
                            stop_name = node_elem.get("tags", {}).get("name")
                            break
                    stops.append({"lat": lat, "lon": lon, "name": stop_name, "line": line_ref})
        if stops:
            routes[line_ref] = stops
            print(f"    Metro {line_ref}: {len(stops)} stops", file=sys.stderr)

    return routes


def fetch_tram_routes(client: httpx.Client) -> dict[str, list[dict]]:
    """Returns: {route_ref: [{"lat", "lon", "name"}, ...]}"""
    bbox = f"{SOFIA_BBOX[0]},{SOFIA_BBOX[1]},{SOFIA_BBOX[2]},{SOFIA_BBOX[3]}"
    query = f"""
[out:json];
relation["route"="tram"]({bbox});
out body;
>;
out skel qt;
"""
    print("  Fetching tram routes from Overpass...", file=sys.stderr)
    data = overpass_query(query, client)
    if not data:
        return {}

    nodes: dict[int, tuple[float, float]] = {}
    node_tags: dict[int, dict] = {}
    for elem in data.get("elements", []):
        if elem["type"] == "node" and "lat" in elem:
            nodes[elem["id"]] = (elem["lat"], elem["lon"])
            node_tags[elem["id"]] = elem.get("tags", {})

    routes: dict[str, list[dict]] = {}
    for elem in data.get("elements", []):
        if elem["type"] != "relation":
            continue
        tags = elem.get("tags", {})
        ref = tags.get("ref", "?")
        stops = []
        seen_nodes: set[int] = set()
        for member in elem.get("members", []):
            if member["type"] == "node":
                node_id = member["ref"]
                if node_id in nodes and node_id not in seen_nodes:
                    seen_nodes.add(node_id)
                    lat, lon = nodes[node_id]
                    name = node_tags.get(node_id, {}).get("name")
                    stops.append({"lat": lat, "lon": lon, "name": name, "line": ref})
        if stops:
            key = str(ref)
            if key not in routes:
                routes[key] = []
            routes[key].extend(stops)

    # Deduplicate stops per route
    for ref in routes:
        seen: set[tuple] = set()
        unique = []
        for s in routes[ref]:
            k = (round(s["lat"], 5), round(s["lon"], 5))
            if k not in seen:
                seen.add(k)
                unique.append(s)
        routes[ref] = unique
        print(f"    Tram {ref}: {len(unique)} stops", file=sys.stderr)

    return routes


def fetch_bus_routes(client: httpx.Client, min_stops: int = 8) -> dict[str, list[dict]]:
    """
    Returns major bus routes (filtered by min_stops count).
    Returns: {route_ref: [{"lat", "lon", "name"}, ...]}
    """
    bbox = f"{SOFIA_BBOX[0]},{SOFIA_BBOX[1]},{SOFIA_BBOX[2]},{SOFIA_BBOX[3]}"
    query = f"""
[out:json];
relation["route"="bus"]["network"~"Sofia|Со[фф]ия",i]({bbox});
out body;
>;
out skel qt;
"""
    print("  Fetching bus routes from Overpass...", file=sys.stderr)
    data = overpass_query(query, client)
    if not data:
        # Fallback: all bus routes in bbox
        query_fallback = f"""
[out:json];
relation["route"="bus"]({bbox});
out body;
>;
out skel qt;
"""
        print("  Retrying with fallback bus query...", file=sys.stderr)
        data = overpass_query(query_fallback, client)
        if not data:
            return {}

    nodes: dict[int, tuple[float, float]] = {}
    node_tags: dict[int, dict] = {}
    for elem in data.get("elements", []):
        if elem["type"] == "node" and "lat" in elem:
            nodes[elem["id"]] = (elem["lat"], elem["lon"])
            node_tags[elem["id"]] = elem.get("tags", {})

    raw_routes: dict[str, list[dict]] = {}
    for elem in data.get("elements", []):
        if elem["type"] != "relation":
            continue
        tags = elem.get("tags", {})
        ref = tags.get("ref", "?")
        stops = []
        seen_nodes: set[int] = set()
        for member in elem.get("members", []):
            if member["type"] == "node":
                node_id = member["ref"]
                if node_id in nodes and node_id not in seen_nodes:
                    seen_nodes.add(node_id)
                    lat, lon = nodes[node_id]
                    name = node_tags.get(node_id, {}).get("name")
                    stops.append({"lat": lat, "lon": lon, "name": name, "line": ref})
        if stops:
            key = str(ref)
            if key not in raw_routes:
                raw_routes[key] = []
            raw_routes[key].extend(stops)

    # Deduplicate + filter by min_stops
    filtered: dict[str, list[dict]] = {}
    for ref, stops in raw_routes.items():
        seen: set[tuple] = set()
        unique = []
        for s in stops:
            k = (round(s["lat"], 5), round(s["lon"], 5))
            if k not in seen:
                seen.add(k)
                unique.append(s)
        if len(unique) >= min_stops:
            filtered[ref] = unique

    print(f"  {len(filtered)} major bus routes (≥{min_stops} stops)", file=sys.stderr)
    return filtered


# ---------------------------------------------------------------------------
# Nominatim geocoding
# ---------------------------------------------------------------------------

def geocode_neighbourhood(name_bg: str, client: httpx.Client) -> Optional[tuple[float, float]]:
    """Return (lat, lon) for a Sofia neighbourhood name, or None."""
    try:
        resp = client.get(
            NOMINATIM_URL,
            params={
                "q": f"{name_bg}, София, България",
                "format": "json",
                "limit": 1,
                "countrycodes": "bg",
            },
            headers={"User-Agent": "bg-realestate-intel/1.0 (research project)"},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json()
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception as e:
        print(f"    Geocode error for '{name_bg}': {e}", file=sys.stderr)
    return None


# ---------------------------------------------------------------------------
# Transport → neighbourhood mapping
# ---------------------------------------------------------------------------

def build_stop_index(
    metro_routes: dict[str, list[dict]],
    tram_routes: dict[str, list[dict]],
    bus_routes: dict[str, list[dict]],
) -> list[dict]:
    """Flatten all stops into a single list with type + route label."""
    stops = []
    for line, route_stops in metro_routes.items():
        for s in route_stops:
            stops.append({**s, "transport_type": "metro", "route": line})
    for line, route_stops in tram_routes.items():
        for s in route_stops:
            stops.append({**s, "transport_type": "tram", "route": line})
    for line, route_stops in bus_routes.items():
        for s in route_stops:
            stops.append({**s, "transport_type": "bus", "route": line})
    return stops


def assign_transport_to_neighbourhood(
    center_lat: float,
    center_lon: float,
    all_stops: list[dict],
) -> dict:
    """Find all transport serving a neighbourhood centre within radius thresholds."""
    metro_lines: set[str] = set()
    nearest_metro: Optional[dict] = None
    nearest_metro_dist = float("inf")
    tram_lines: set[str] = set()
    bus_lines: set[str] = set()

    for stop in all_stops:
        dist = haversine_m(center_lat, center_lon, stop["lat"], stop["lon"])
        t = stop["transport_type"]
        route = stop["route"]

        if t == "metro" and dist <= METRO_RADIUS_M:
            metro_lines.add(route)
            if dist < nearest_metro_dist:
                nearest_metro_dist = dist
                nearest_metro = {"name": stop.get("name"), "line": route, "distance_m": round(dist)}

        elif t == "tram" and dist <= TRAM_RADIUS_M:
            tram_lines.add(route)

        elif t == "bus" and dist <= BUS_RADIUS_M:
            bus_lines.add(route)

    return {
        "metro": len(metro_lines) > 0,
        "metro_lines": sorted(metro_lines),
        "nearest_metro_station": nearest_metro["name"] if nearest_metro else None,
        "nearest_metro_distance_m": nearest_metro["distance_m"] if nearest_metro else None,
        "tram_lines": sorted(tram_lines),
        "bus_lines": sorted(bus_lines),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Sofia public transport data fetcher")
    parser.add_argument(
        "--output",
        default="data/raw/transport/sofia_transport.json",
        help="Output JSON file path",
    )
    parser.add_argument(
        "--min-bus-stops",
        type=int,
        default=8,
        help="Minimum stops for a bus route to be considered 'major' (default: 8)",
    )
    args = parser.parse_args()

    output_path = pathlib.Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with httpx.Client(follow_redirects=True) as client:
        # --- Fetch all transport data ---
        print("Step 1/3: Fetching transport routes from OpenStreetMap...", file=sys.stderr)
        metro_routes = fetch_metro_routes(client)
        time.sleep(1)
        tram_routes = fetch_tram_routes(client)
        time.sleep(1)
        bus_routes = fetch_bus_routes(client, min_stops=args.min_bus_stops)
        time.sleep(1)

        all_stops = build_stop_index(metro_routes, tram_routes, bus_routes)
        print(f"\n  Total stops indexed: {len(all_stops)}", file=sys.stderr)
        print(f"  Metro routes: {sorted(metro_routes.keys())}", file=sys.stderr)
        print(f"  Tram routes: {sorted(tram_routes.keys())}", file=sys.stderr)
        print(f"  Bus routes: {len(bus_routes)} routes", file=sys.stderr)

        # --- Geocode neighbourhoods ---
        print("\nStep 2/3: Geocoding Sofia neighbourhoods via Nominatim...", file=sys.stderr)
        neighbourhood_centers: dict[str, tuple[float, float]] = {}

        for i, (slug, name_bg) in enumerate(SOFIA_NEIGHBOURHOODS, 1):
            print(f"  [{i}/{len(SOFIA_NEIGHBOURHOODS)}] {name_bg}...", file=sys.stderr, end=" ")
            coords = geocode_neighbourhood(name_bg, client)
            if coords:
                neighbourhood_centers[slug] = coords
                print(f"✓ ({coords[0]:.4f}, {coords[1]:.4f})", file=sys.stderr)
            else:
                print("✗ not found", file=sys.stderr)
            time.sleep(1.1)  # Nominatim rate limit: max 1 req/sec

        # --- Map transport to neighbourhoods ---
        print("\nStep 3/3: Mapping transport to neighbourhoods...", file=sys.stderr)
        result: dict[str, dict] = {}

        for slug, name_bg in SOFIA_NEIGHBOURHOODS:
            if slug not in neighbourhood_centers:
                result[slug] = {
                    "name": name_bg,
                    "geocode_failed": True,
                    "metro": False,
                    "metro_lines": [],
                    "nearest_metro_station": None,
                    "nearest_metro_distance_m": None,
                    "tram_lines": [],
                    "bus_lines": [],
                }
                continue

            lat, lon = neighbourhood_centers[slug]
            transport = assign_transport_to_neighbourhood(lat, lon, all_stops)
            result[slug] = {"name": name_bg, **transport}

            metro_tag = f"🚇 {transport['metro_lines']}" if transport["metro"] else "no metro"
            tram_tag = f"🚋 {transport['tram_lines']}" if transport["tram_lines"] else ""
            print(f"  {slug}: {metro_tag} {tram_tag}", file=sys.stderr)

    # --- Save output ---
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ Saved transport data for {len(result)} neighbourhoods → {output_path}", file=sys.stderr)

    # Quick summary
    metro_count = sum(1 for v in result.values() if v.get("metro"))
    tram_count = sum(1 for v in result.values() if v.get("tram_lines"))
    print(f"   Metro access: {metro_count} neighbourhoods", file=sys.stderr)
    print(f"   Tram access:  {tram_count} neighbourhoods", file=sys.stderr)


if __name__ == "__main__":
    main()
