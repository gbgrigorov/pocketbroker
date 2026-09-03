#!/usr/bin/env python3
"""One-off helper: append parsed legalacts results for one company to the
Zhekov registry jsonl + mark it done in the progress tsv."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data/raw/signals/sofia/registry_zhekov_2026-06-14.jsonl"
PROGRESS = ROOT / "data/raw/signals/sofia/registry_zhekov_progress.tsv"


def main():
    eik, name, acts_path = sys.argv[1], sys.argv[2], sys.argv[3]
    acts = json.loads(Path(acts_path).read_text(encoding="utf-8"))

    with REGISTRY.open("a", encoding="utf-8") as f:
        for a in acts:
            case_bits = " ".join(x for x in (a.get("court"), f"дело {a['case']}" if a.get("case") else None, a.get("case_type")) if x)
            title = f"{a.get('court','')}, {a.get('act_type','Съдебен акт')} {a.get('num','')} от {a.get('observed','')} по {a.get('case_type','')} {a.get('case','')}"
            row = {
                "matched_eik": eik,
                "matched_name": name,
                "url": f"https://legalacts.justice.bg/Search/Details?actId={a['actid']}",
                "title": " ".join(title.split()),
                "snippet": case_bits + (f" · в сила {a['inforce']}" if a.get("inforce") else ""),
                "source_site": "legalacts.justice.bg",
                "observed_date": a.get("observed_iso") or a.get("observed"),
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # update progress tsv
    lines = PROGRESS.read_text(encoding="utf-8").splitlines()
    out = []
    for ln in lines:
        parts = ln.split("\t")
        if len(parts) >= 4 and parts[0] == eik:
            parts[3] = "1"
            if len(parts) < 5:
                parts.append(str(len(acts)))
            else:
                parts[4] = str(len(acts))
            ln = "\t".join(parts)
        out.append(ln)
    PROGRESS.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"appended {len(acts)} acts for {eik} {name}")


if __name__ == "__main__":
    main()
