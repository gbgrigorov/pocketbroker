"""Generate sitemap.xml for the BG INTEL frontend (History-mode routes).

Usage:
    .venv/bin/python scripts/generate_sitemap.py [output_path]

Reads SITE_URL from the environment (defaults to the production domain) and
DATABASE_URL via app.db.SessionLocal (same as the API/ETL). Writes a single
sitemap covering: static pages, city price maps, neighbourhood deep-dives,
and company entity profiles (persons are excluded for privacy).
"""

from __future__ import annotations

import os
import sys
from xml.sax.saxutils import escape

from sqlalchemy import select

from app.db import SessionLocal
from app.models import City, Entity, Neighbourhood

SITE_URL = os.environ.get("SITE_URL", "https://app.example.com").rstrip("/")

STATIC_PATHS = [
    "/",
    "/entities",
    "/about",
    "/location",
    "/terms",
    "/privacy",
    "/disclaimer",
]


def collect_urls(session) -> list[str]:
    paths = list(STATIC_PATHS)

    cities = session.scalars(select(City)).all()
    city_slug_by_id = {}
    for city in cities:
        paths.append(f"/c/{city.slug}")
        city_slug_by_id[city.id] = city.slug

    for n in session.scalars(select(Neighbourhood)):
        city_slug = city_slug_by_id.get(n.city_id)
        if city_slug and n.slug:
            paths.append(f"/c/{city_slug}/n/{n.slug}")

    # Companies only — person entities are excluded from the public sitemap.
    entities = session.scalars(
        select(Entity).where(
            Entity.kind == "company",
            Entity.eik.isnot(None),
            Entity.slug.isnot(None),
        )
    )
    for e in entities:
        paths.append(f"/e/{e.eik}/{e.slug}")

    return paths


def render_sitemap(paths: list[str]) -> str:
    urls = "\n".join(
        f"  <url><loc>{escape(SITE_URL + path)}</loc></url>" for path in paths
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}\n"
        "</urlset>\n"
    )


def main() -> None:
    output_path = sys.argv[1] if len(sys.argv) > 1 else "sitemap.xml"
    session = SessionLocal()
    try:
        paths = collect_urls(session)
    finally:
        session.close()

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(render_sitemap(paths))

    print(f"Wrote {len(paths)} URLs to {output_path}")


if __name__ == "__main__":
    main()
