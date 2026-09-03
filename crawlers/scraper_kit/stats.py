"""Aggregate per-run telemetry into a single headline counter.

Walks every ``*.stats.json`` manifest under ``data/raw/`` and rolls them into
``data/stats/crawl_stats.json`` — the "how much data did the crawlers process"
flex number surfaced at ``GET /api/stats``.

    python3 -m crawlers.scraper_kit.stats
"""

from __future__ import annotations

import datetime as _dt
import glob
import json
from pathlib import Path

from crawlers.scraper_kit.base import DATA_ROOT


def aggregate() -> dict:
    manifests = glob.glob(str(DATA_ROOT / "raw" / "**" / "*.stats.json"), recursive=True)

    totals = dict(
        runs=0, pages_fetched=0, bytes_downloaded=0,
        records_parsed=0, records_emitted=0, errors=0,
    )
    sites: set[str] = set()
    scopes: set[str] = set()
    started: list[str] = []
    per_domain: dict[str, dict] = {}

    for path in manifests:
        try:
            d = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        totals["runs"] += 1
        for k in ("pages_fetched", "bytes_downloaded", "records_parsed", "records_emitted", "errors"):
            totals[k] += d.get(k, 0)
        if d.get("site"):
            sites.add(d["site"])
        if d.get("scope"):
            scopes.add(d["scope"])
        if d.get("started_at"):
            started.append(d["started_at"])
        dom = per_domain.setdefault(d.get("domain", "?"), {"records_emitted": 0, "bytes_downloaded": 0})
        dom["records_emitted"] += d.get("records_emitted", 0)
        dom["bytes_downloaded"] += d.get("bytes_downloaded", 0)

    out = {
        **totals,
        "data_scanned_mb": round(totals["bytes_downloaded"] / 1e6, 2),
        "data_scanned_gb": round(totals["bytes_downloaded"] / 1e9, 4),
        "data_points": totals["records_emitted"],
        "distinct_sites": sorted(sites),
        "distinct_scopes": sorted(scopes),
        "per_domain": per_domain,
        "earliest_run": min(started) if started else None,
        "latest_run": max(started) if started else None,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
    }

    out_dir = DATA_ROOT / "stats"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "crawl_stats.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return out


def main() -> None:
    out = aggregate()
    print(
        f"crawl_stats: {out['runs']} runs · {out['data_scanned_mb']} MB scanned · "
        f"{out['data_points']} data points · sites={out['distinct_sites']} · "
        f"scopes={out['distinct_scopes']}"
    )


if __name__ == "__main__":
    main()
