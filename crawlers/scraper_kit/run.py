"""CLI orchestrator — run one or more site scrapers for one or more cities.

Examples::

    # New-building projects for Sofia, every registered new-building site:
    python3 -m crawlers.scraper_kit.run --domain new_buildings --city sofia --site all

    # A single site for two cities:
    python3 -m crawlers.scraper_kit.run --domain new_buildings --city sofia,plovdiv --site novitesgradi

    # National builders register (scope is the country, not a city):
    python3 -m crawlers.scraper_kit.run --domain builders --site all

After scraping, refresh the headline counter::

    python3 -m crawlers.scraper_kit.stats
"""

from __future__ import annotations

import argparse
import sys

from crawlers.scraper_kit import sites as sites_pkg
from crawlers.scraper_kit.cities import get_city


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", required=True, choices=["builders", "new_buildings"])
    parser.add_argument("--site", default="all", help="site key, comma-separated list, or 'all'")
    parser.add_argument(
        "--city",
        default="",
        help="city slug(s), comma-separated (new_buildings domain). Ignored for builders.",
    )
    parser.add_argument("--country", default="bg", help="country scope for the builders domain")
    args = parser.parse_args()

    available = sites_pkg.discover(domain=args.domain)
    if not available:
        raise SystemExit(f"No site scrapers found for domain '{args.domain}'.")

    if args.site == "all":
        site_keys = sorted(available)
    else:
        site_keys = [s.strip() for s in args.site.split(",") if s.strip()]
        unknown = [s for s in site_keys if s not in available]
        if unknown:
            raise SystemExit(
                f"Unknown site(s) for domain '{args.domain}': {', '.join(unknown)}. "
                f"Available: {', '.join(sorted(available))}"
            )

    # Determine scopes: builders = country; new_buildings = each city slug.
    if args.domain == "builders":
        scopes = [args.country]
    else:
        if not args.city:
            raise SystemExit("--city is required for the new_buildings domain.")
        scopes = [c.strip() for c in args.city.split(",") if c.strip()]
        for slug in scopes:
            get_city(slug)  # validate early

    outputs = []
    for slug in scopes:
        for key in site_keys:
            scraper_cls = available[key]
            print(f">>> {args.domain}/{key} scope={slug}", file=sys.stderr)
            try:
                outputs.append(scraper_cls(slug).run())
            except Exception as exc:  # noqa: BLE001 - one site failing must not abort the rest
                print(f"!!! {key}/{slug} failed: {exc}", file=sys.stderr)

    print(f"done: {len(outputs)} run(s) written.", file=sys.stderr)


if __name__ == "__main__":
    main()
