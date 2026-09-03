"""Builder normalizer — merge КСБ + BRRA + signal feeds into one record per ЕИК.

Reads every ``data/raw/builders/<country>/*.jsonl`` (one file per site/run) and
produces ``data/normalized/builders/<country>.jsonl`` — one canonical builder
per ЕИК, with per-field provenance and a ``sources`` list of contributing sites.

Field precedence (most authoritative wins; missing values fall through):
    name           : brra_opendata > ksb
    legal_form,
    address, capital_bgn, status, owners, managers, financials : brra_opendata
    ksb_category, ksb_active : ksb
    insolvency_flag, cases   : aistn
    tax_debt_bgn             : nap

    python3 -m crawlers.normalize.builders --country bg
"""

from __future__ import annotations

import argparse
import glob
import json
import re
from collections import OrderedDict
from typing import Dict, Iterable

from crawlers.normalize import DATA_ROOT

# Which site supplies which fields, in precedence order (first present wins).
_FIELD_SOURCES = OrderedDict([
    ("name", ["brra_opendata", "ksb"]),
    ("legal_form", ["brra_opendata"]),
    ("address", ["brra_opendata", "ksb"]),
    ("capital_bgn", ["brra_opendata"]),
    ("status", ["brra_opendata"]),
    ("owners", ["brra_opendata"]),
    ("managers", ["brra_opendata"]),
    ("financials", ["brra_opendata"]),
    ("ksb_category", ["ksb"]),
    ("ksb_active", ["ksb"]),
    ("insolvency_flag", ["aistn"]),
    ("cases", ["aistn"]),
    ("tax_debt_bgn", ["nap"]),
])


def clean_eik(value) -> str | None:
    """Normalise an ЕИК to its digit string (9 or 13 digits); None if implausible."""
    if value is None:
        return None
    digits = re.sub(r"\D", "", str(value))
    return digits if len(digits) in (9, 10, 13) else None


def load_jsonl(path: str) -> Iterable[dict]:
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def merge(records_by_site: Dict[str, dict], latest_scraped: str | None) -> dict:
    """Combine the per-site records for one ЕИК into a canonical builder dict."""
    out: dict = {}
    for field, site_order in _FIELD_SOURCES.items():
        for site in site_order:
            rec = records_by_site.get(site)
            if rec and rec.get(field) not in (None, "", [], {}):
                out[field] = rec[field]
                break
    out["last_checked_at"] = latest_scraped
    out["sources"] = sorted(records_by_site)
    return out


def normalize_country(country: str) -> tuple[int, int]:
    raw_glob = str(DATA_ROOT / "raw" / "builders" / country / "*.jsonl")
    files = sorted(glob.glob(raw_glob))

    # eik -> {site: record}, plus the latest scraped_at seen for that eik
    grouped: Dict[str, Dict[str, dict]] = {}
    latest: Dict[str, str] = {}
    raw_rows = 0
    for path in files:
        for rec in load_jsonl(path):
            raw_rows += 1
            eik = clean_eik(rec.get("eik"))
            if not eik:
                continue
            site = rec.get("source_site", "unknown")
            grouped.setdefault(eik, {})[site] = rec
            ts = rec.get("scraped_at")
            if ts and (eik not in latest or ts > latest[eik]):
                latest[eik] = ts

    out_dir = DATA_ROOT / "normalized" / "builders"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{country}.jsonl"
    with out_path.open("w", encoding="utf-8") as fh:
        for eik, by_site in sorted(grouped.items()):
            rec = merge(by_site, latest.get(eik))
            rec["eik"] = eik
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    return raw_rows, len(grouped)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country", default="bg")
    args = parser.parse_args()
    raw_rows, canonical = normalize_country(args.country)
    print(f"builders[{args.country}]: {raw_rows} raw rows -> {canonical} canonical builders")


if __name__ == "__main__":
    main()
