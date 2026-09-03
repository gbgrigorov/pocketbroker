"""legalacts.justice.bg — published court acts, official-tier signals.

The search form is CAPTCHA-protected (a `/captcha.ashx` image). We do NOT defeat
it: we download the image, show it to a human operator, and read the code from
stdin. Low-volume, shortlist-only — one human CAPTCHA per company. An act is kept
only when the company ЕИК appears in the act text (defamation-safe).

    # interactive — a human must type each CAPTCHA:
    python3 -m crawlers.scraper_kit.sites.legalacts --shortlist data/seed/legalacts_shortlist.tsv
    python3 -m crawlers.scraper_kit.sites.legalacts --eik 175155346 --name "АРТЕКС ИНЖЕНЕРИНГ АД"
    python3 -m crawlers.scraper_kit.sites.legalacts --eik 175155346 --name "АРТЕКС ИНЖЕНЕРИНГ АД" --capture
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

from crawlers.scraper_kit.base import BaseScraper

BASE = "https://legalacts.justice.bg"
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def _hidden(html: str, name: str) -> Optional[str]:
    m = re.search(rf'name="{re.escape(name)}"[^>]*value="([^"]*)"', html)
    if m:
        return m.group(1)
    m = re.search(rf'value="([^"]*)"[^>]*name="{re.escape(name)}"', html)
    return m.group(1) if m else None


def parse_results(html: str) -> List[dict]:
    """Extract act rows from a legalacts results page.

    Each act is an ``<a href="/Search/Details?actId=…">`` whose own text carries
    the row metadata ("Вид акт: … Акт номер: … от DD.MM.YYYY … Съд: … Дело номер:
    … Вид дело: …"). Acts are anonymised — there is no party name or ЕИК here, so
    these rows are *candidates*: a human confirms the company before they become
    official-tier signals. Returns ``[{url,title,court,case,observed,snippet}]``.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    rows: List[dict] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/Search/Details?actId=" not in href:
            continue
        url = href if href.startswith("http") else f"{BASE}{href}"
        t = re.sub(r"\s+", " ", a.get_text(" ", strip=True))

        def grab(pat: str) -> Optional[str]:
            m = re.search(pat, t)
            return (m.group(1).strip() or None) if m else None

        vid = grab(r"Вид акт:\s*(.+?)\s*Акт номер")
        num = grab(r"Акт номер:\s*(.+?)\s*(?:от |В сила)")
        observed = grab(r"от\s*(\d{1,2}\.\d{1,2}\.\d{4})")
        court = grab(r"Съд:\s*(.+?)\s*Дело номер")
        case = grab(r"Дело номер:\s*(.+?)\s*Вид дело")
        vd = grab(r"Вид дело:\s*(.+)$")

        title = " ".join(p for p in (vid, num) if p) or "Съдебен акт"
        snippet = " · ".join(x for x in (court,
                                         f"дело {case}" if case else None, vd) if x) or None
        rows.append({"url": url, "title": title, "court": court, "case": case,
                     "observed": observed, "snippet": snippet})

    seen, out = set(), []
    for r in rows:
        if r["url"] in seen:
            continue
        seen.add(r["url"])
        out.append(r)
    return out


class LegalactsScraper(BaseScraper):
    site = "legalacts"
    domain = "signals"
    rate_limit_s = 2.0  # be gentle with public-justice infrastructure

    def __init__(self, scope: str, targets: List[Tuple[str, str]], capture: bool = False,
                 method: str = "eik"):
        super().__init__(scope)
        self.targets = targets          # [(eik, name)]
        self.capture = capture
        self.method = method            # 'eik' (ЕИК digits) | 'name'
        # One entry per search we actually completed, zero-result ones included —
        # written to legalacts_checks_*.jsonl so the DB can answer "did we check
        # this company, and when?". A search with no acts leaves no signal row,
        # so without this log a clean company is indistinguishable from an
        # unchecked one.
        self.checks: List[dict] = []

    # --- CAPTCHA-gated search ------------------------------------------------

    def _solve_and_search(self, name: str) -> Optional[str]:
        """GET the form, prompt the human for the CAPTCHA, POST the search.

        Returns the results HTML, or None if the operator skips/abort.
        """
        page = self.get(f"{BASE}/").text
        token = _hidden(page, "__RequestVerificationToken")
        guid = _hidden(page, "captcha-guid")
        if not token or not guid:
            self._log("could not locate antiforgery token / captcha-guid; site changed?")
            return None

        # Download + show the CAPTCHA image to the operator.
        img = self._client.get(f"{BASE}/captcha.ashx", params={"guid": guid})
        tmp = Path(tempfile.gettempdir()) / f"legalacts_captcha_{guid[:8]}.png"
        tmp.write_bytes(img.content)
        self._show(tmp)
        code = input(f"[legalacts] CAPTCHA code for '{name}' (blank to skip): ").strip()
        if not code:
            return None

        data = {
            "IsAdvanced": "True",
            "__RequestVerificationToken": token,
            "CourtId": "", "CaseKindId": "", "CaseNumber": "", "CaseYear": "",
            "Judge": "", "ActKindId": "", "StatusId": "", "ActNumber": "", "ActYear": "",
            "DateFrom": "", "DateTo": "", "ECLI": "",
            "KeyWord": name,
            "IsLuceneInUse": "true",
            "ShowConnected": "false",
            "Captcha": code,
            "captcha-guid": guid,
        }
        resp = self._client.post(f"{BASE}/", data=data)
        self.stats.pages_fetched += 1
        self.stats.bytes_downloaded += len(resp.content)
        html = resp.text
        if "captcha" in html.lower() and "Невалиден" in html:
            self._log("CAPTCHA rejected; retrying once.")
            return self._solve_and_search(name)
        return html

    def _show(self, path: Path) -> None:
        """Open the CAPTCHA image for the operator (macOS `open`; fallback: print path)."""
        try:
            if sys.platform == "darwin":
                subprocess.run(["open", str(path)], check=False)
            else:
                self._log(f"CAPTCHA image saved to {path} — open it to read the code.")
        except Exception:  # noqa: BLE001
            self._log(f"CAPTCHA image saved to {path}")

    def scrape(self) -> Iterator[dict]:
        import datetime as _dt
        from crawlers.signals.official import act_mentions_eik, to_registry_row
        today = _dt.date.today().isoformat()
        for eik, name in self.targets:
            html = self._solve_and_search(name)
            if html is None:
                continue
            if self.capture:
                out = FIXTURES / f"legalacts_results_{eik}.html"
                out.write_text(html, encoding="utf-8")
                self._log(f"captured results HTML -> {out}")
                continue
            rows = parse_results(html)
            self._log(f"{name} ({eik}): {len(rows)} candidate acts")
            # Log the search itself before filtering — a 0-act result is a real,
            # useful outcome ("we looked, nothing there"), not an absence of data.
            self.checks.append({
                "eik": eik, "name": name, "method": self.method,
                "acts_found": len(rows), "source_site": "legalacts.justice.bg",
                "checked_at": _dt.datetime.now().isoformat(timespec="seconds"),
            })
            for row in rows:
                try:
                    act_html = self.get(row["url"]).text
                except Exception as exc:  # noqa: BLE001
                    self._log(f"  skip {row['url']}: {exc}")
                    continue
                if not act_mentions_eik(act_html, eik):
                    self._log(f"  skip (EIK not found): {row['title']}")
                    continue
                yield to_registry_row(
                    eik=eik, name=name, url=row["url"],
                    title=row["title"], snippet=row["snippet"],
                    observed=today,
                )


    def run(self) -> Path:
        """Normal run, plus a companion ``legalacts_checks_*.jsonl`` search log.

        The acts file only ever contains hits. The checks file lists every ЕИК we
        searched with its result count, so ``etl.run_signals`` can populate
        ``court_check`` and the admin inbox can show a truthful "checked on <date>"
        for companies that came back clean.
        """
        import json as _json

        out_path = super().run()
        if not self.checks:
            return out_path
        checks_path = out_path.with_name(
            out_path.name.replace(f"{self.site}_", f"{self.site}_checks_", 1)
        )
        with checks_path.open("w", encoding="utf-8") as fh:
            for rec in self.checks:
                fh.write(_json.dumps(rec, ensure_ascii=False) + "\n")
        self._log(f"{len(self.checks)} court checks -> {checks_path}")
        return out_path


def _load_shortlist(path: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    with open(path, encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.rstrip("\n")
            if not ln.strip() or ln.lstrip().startswith("#"):
                continue
            parts = ln.split("\t")
            if len(parts) >= 2 and parts[0].strip():
                out.append((re.sub(r"\D", "", parts[0]), parts[1].strip()))
    return out


def _cli() -> None:
    import argparse
    p = argparse.ArgumentParser(description="legalacts court-acts assistant (human CAPTCHA)")
    p.add_argument("--scope", default="sofia")
    p.add_argument("--shortlist")
    p.add_argument("--eik")
    p.add_argument("--name")
    p.add_argument("--capture", action="store_true",
                  help="save raw results HTML to fixtures instead of emitting rows")
    args = p.parse_args()

    if args.shortlist:
        targets = _load_shortlist(args.shortlist)
    elif args.eik and args.name:
        targets = [(re.sub(r"\D", "", args.eik), args.name)]
    else:
        p.error("provide --shortlist or (--eik and --name)")
    LegalactsScraper(args.scope, targets, capture=args.capture).run()


if __name__ == "__main__":
    _cli()
