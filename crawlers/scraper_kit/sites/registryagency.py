"""Търговски регистър (portal.registryagency.bg) ownership scraper.

**Replaces papagal.py**, which went behind a Cloudflare managed challenge on
2026-08-20 (`cf-mitigated: challenge`, 403 on every path including the
homepage, unclearable by headless Chromium).

This reads the *official* register instead of a third-party aggregator, via the
JSON endpoint the portal's own "Актуално състояние" page calls:

    GET /CR/api/Deeds/{eik}?entryDate=<iso>&loadFieldsFromAllLegalForms=false

No CAPTCHA, no session, no JS — plain HTTP returning JSON. The HTML page at
`/CR/en/Reports/ActiveConditionTabResult` renders client-side and is useless to
scrape; always use the API.

Output records are **the same shape papagal emitted**, so `etl.load_ownership`
consumes them unchanged.

What this gives us that papagal did not:
  * `activity` — обхват на дейност, which is how we tell a builder from a shop
  * `seizures` — запор върху дружествен дял (share attachments) with creditor,
    enforcement case number and the amount of capital affected. A serious
    distress signal, and one that never appears in legalacts.justice.bg because
    enforcement runs before a частен съдебен изпълнител, not a court.

### person_key — read this before trusting a merge

Papagal minted an opaque per-person hash. The register has no public person id
(it keys on ЕГН, which is not disclosed), so we derive a deterministic key from
the normalised name, namespaced `tr-` to keep it clearly distinct from
papagal's hashes.

**Two people with the same three-part name therefore collide, and the same
person recorded under both sources gets two nodes.** Neither is silently
resolved here: reconciliation against existing papagal keys is a separate,
reviewable step (`--person-key-map`), never an automatic name merge.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Dict, Iterator, List, Optional

from crawlers.scraper_kit.base import BaseScraper

API = "https://portal.registryagency.bg/CR/api/Deeds"
API_SUBJECTS = f"{API}/Subjects"            # name -> [{isPhysical, ident, name}]
API_SUBJECT_FIELDS = f"{API}/SubjectInFields"  # ident -> [{companyFullName, uic, fieldName}]

# `deedStatus` on the Deeds payload. 1 is the overwhelming majority (active);
# anything else is treated as unknown rather than guessed at, because mislabelling
# a live company as struck off is worse than leaving the field null.
DEED_STATUS = {1: "Активен"}

# Which ТР field a participation came from tells us the relation.
FIELD_ROLE = {
    "CR_F_7_L": ("management", "Управител"),
    "CR_F_19_L": ("ownership", "Съдружник"),
    "CR_F_23_L": ("ownership", "Едноличен собственик на капитала"),
}

# ТР field numbers -> our names. Codes are stable across legal forms.
F_EIK, F_NAME, F_FORM = "CR_F_1_L", "CR_F_2_L", "CR_F_3_L"
F_ADDRESS, F_ACTIVITY = "CR_F_5_L", "CR_F_6_L"
F_MANAGERS, F_PARTNERS, F_SOLE_OWNER = "CR_F_7_L", "CR_F_19_L", "CR_F_23_L"
F_CAPITAL = "CR_F_31_L"
# Запор върху дял (section CR_APP_ARREST_SHARE_L)
F_SEIZURE_CREDITOR, F_SEIZURE_BASIS, F_SEIZURE_SHARE = "CR_F_401_L", "CR_F_403_L", "CR_F_406_L"
ARREST_SECTION = "CR_APP_ARREST_SHARE_L"

# The register writes this instead of blanking a field that no longer applies.
DELETED = "Заличено обстоятелство"

BGN_PER_EUR = 1.95583


def _text(html) -> str:
    """Strip the field's HTML fragment down to plain text."""
    if html is None:
        return ""
    if not isinstance(html, str):
        html = json.dumps(html, ensure_ascii=False)
    t = re.sub(r"<[^>]+>", " ", html)
    t = t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"')
    return re.sub(r"\s+", " ", t).strip()


def _norm_person(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def person_key(name: str) -> str:
    """Deterministic, source-namespaced person id. See the module docstring."""
    digest = hashlib.sha256(_norm_person(name).encode("utf-8")).hexdigest()
    return f"tr-{digest}-1"


def _split_participants(blob: str) -> List[dict]:
    """Parse a managers/partners/sole-owner field into participant dicts.

    Entries are concatenated with no separator, and come in two kinds:

        Име Презиме Фамилия, Държава: БЪЛГАРИЯ, Размер на дяловото участие: N лв.
        "ФИРМА" ЕООД, ЕИК/ПИК 123456789, Държава: БЪЛГАРИЯ, Размер ...: N лв.

    Company participants matter as much as people — a company partner is how an
    SPV chain is actually built — so both are returned, tagged by ``kind``.

    Returns [{kind, name, eik|None, share_bgn|None}].

    Known limitation: when the register lists two people under a single
    ``Държава:`` value ("ИВАН ПЕТРОВ ГЕОРГИЕВ МАРИЯ ИВАНОВА ПЕТРОВА, Държава:
    БЪЛГАРИЯ") the boundary is genuinely ambiguous and only the trailing name is
    recovered. Seen on ЕИК 120564924. Such fields need review by hand.
    """
    if not blob or DELETED in blob:
        return []

    entry = re.compile(
        # Digits belong inside a name token: "Б2Б МЕДИЯ ХОЛДИНГ СЕ" lost its 2 and
        # came out as "Б МЕДИЯ ХОЛДИНГ СЕ" while this class was letters-only.
        r'(?P<name>"[^"]+"[^,]*|[А-ЯЁ][А-ЯЁа-яё0-9\-]*(?:\s+[А-ЯЁ0-9][А-ЯЁа-яё0-9\-]*){1,4})'
        r'\s*,\s*'
        r'(?:ЕИК/ПИК\s*(?P<eik>\d{9,13})\s*,\s*)?'
        # A FOREIGN owner carries a home-register id instead of an ЕИК
        # ("…, Идентификация HRB 34711, Чуждестранно юридическо лице, Държава: ГЕРМАНИЯ").
        # Without this the whole entry failed to match and the owner vanished —
        # every company with a foreign parent looked ownerless. Seen on ЕИК 205890369.
        r'(?:Идентификация\s*(?P<foreign_id>[^,]+?)\s*,\s*)?'
        r'(?:Чуждестранно юридическо лице\s*,\s*)?'
        r'(?:Държава|Страна)'
    )
    share_re = re.compile(r"дялово(?:то)?\s+участие:\s*([\d.,]+)")

    out: List[dict] = []
    matches = list(entry.finditer(blob))
    for i, m in enumerate(matches):
        tail = blob[m.end(): matches[i + 1].start() if i + 1 < len(matches) else len(blob)]
        share = share_re.search(tail)
        name = re.sub(r"\s+", " ", m.group("name")).replace('"', "").strip()
        # A name can pick up the previous entry's country value ("Държава: БЪЛГАРИЯ
        # ИВАН ..."), because the match starts right after it. Drop the leading token.
        name = re.sub(r"^(?:БЪЛГАРИЯ|България)\s+", "", name).strip()
        foreign = m.groupdict().get("foreign_id")
        out.append({
            # A foreign id (HRB, CHE, …) means a company just as much as an ЕИК does.
            "kind": "company" if (m.group("eik") or foreign) else "person",
            "name": name,
            "eik": m.group("eik"),
            "foreign_id": foreign.strip() if foreign else None,
            "share_bgn": float(share.group(1).replace(",", "")) if share else None,
        })
    return out


def _capital_eur(blob: str) -> Optional[float]:
    """Field 31 is already in EUR since the 2026 changeover; лв. still appears
    on older records that have not been restated."""
    if not blob:
        return None
    m = re.search(r"([\d\s]+[.,]?\d*)\s*(€|лв)", blob.replace(" ", " "))
    if not m:
        return None
    try:
        amount = float(m.group(1).replace(" ", "").replace(",", "."))
    except ValueError:
        return None
    return amount if m.group(2) == "€" else round(amount / BGN_PER_EUR, 2)


class RegistryAgencyScraper(BaseScraper):
    site = "registryagency"
    domain = "ownership"
    rate_limit_s = 3.0  # portal returns 429 at ~1 req/s; 3s is safe

    def __init__(self, scope: str = "bg", eiks: Optional[List[str]] = None,
                 key_map: Optional[Dict[str, str]] = None,
                 persons: Optional[List[str]] = None):
        super().__init__(scope)
        self.eiks = eiks or []
        self.persons = persons or []  # depth-2: person names to expand
        if self.persons:
            self.file_tag = "persons"  # keep depth-2 output distinct, as papagal did
        # Optional {normalised name: existing person_key} so a re-scrape attaches
        # to nodes already in the graph instead of minting parallel tr- ones.
        self.key_map = {_norm_person(k): v for k, v in (key_map or {}).items()}

    def _key_for(self, name: str) -> str:
        return self.key_map.get(_norm_person(name)) or person_key(name)

    def _fields(self, deed: dict):
        """Yield (section_nameCode, field_nameCode, text, entry_date)."""
        for section in deed.get("sections") or []:
            for sub in section.get("subDeeds") or []:
                for group in sub.get("groups") or []:
                    for f in group.get("fields") or []:
                        yield (section.get("nameCode"), f.get("nameCode"),
                               _text(f.get("htmlData")), f.get("fieldEntryDate"))

    def _seizures(self, deed: dict) -> List[dict]:
        out = []
        for section in deed.get("sections") or []:
            if section.get("nameCode") != ARREST_SECTION:
                continue
            for sub in section.get("subDeeds") or []:
                cur: Dict[str, str] = {}
                for group in sub.get("groups") or []:
                    for f in group.get("fields") or []:
                        code, val = f.get("nameCode"), _text(f.get("htmlData"))
                        if not val:
                            continue
                        if code == F_SEIZURE_CREDITOR:
                            cur["creditor"] = val
                        elif code == F_SEIZURE_BASIS:
                            cur["basis"] = val
                            case = re.search(r"Дело №:\s*(\S+)", val)
                            if case:
                                cur["case_no"] = case.group(1)
                        elif code == F_SEIZURE_SHARE:
                            cur["share"] = val
                            amt = re.search(r"([\d]+[.,]\d{2})\s*лв", val)
                            if amt:
                                cur["share_bgn"] = float(amt.group(1).replace(",", "."))
                            # Two shapes seen in the wild:
                            #   "...съответства ... 1300.00 лв. ИМЕ ПРЕЗИМЕ ФАМИЛИЯ, Държава: ..."
                            #   "дружествен дял на ИМЕ ПРЕЗИМЕ ФАМИЛИЯ"   (no amount; e.g. an
                            #   НАП/АДВ tax attachment, ЕИК 175250894)
                            who = (re.search(r"лв\.\s*([А-ЯЁ][А-ЯЁа-яё\-\s]+?),\s*Държава", val)
                                   or re.search(r"дял\s+на\s+([А-ЯЁ][А-ЯЁа-яё\-\s]+?)\s*$", val))
                            if who:
                                cur["holder"] = re.sub(r"\s+", " ", who.group(1)).strip()
                        if f.get("fieldEntryDate"):
                            cur.setdefault("entry_date", f["fieldEntryDate"])
                # A sub-deed can carry only a sequence number with no substance;
                # emitting it would produce a signal reading "запор None лв".
                if cur.get("creditor") or cur.get("share_bgn"):
                    out.append(cur)
        return out

    def _record(self, eik: str, deed: dict) -> dict:  # noqa: C901
        vals: Dict[str, str] = {}
        founded = None
        for section_code, code, val, entry_date in self._fields(deed):
            if section_code == ARREST_SECTION or not val:
                continue
            vals.setdefault(code, val)
            if code == F_NAME and founded is None and entry_date:
                founded = entry_date[:4]

        related: List[dict] = []

        foreign_owners: List[dict] = []

        def add(field: str, relation: str, role: str) -> None:
            for p in _split_participants(vals.get(field, "")):
                # A foreign parent has no ЕИК, so it cannot be a graph node keyed
                # the way every other company is. Recording it as a related company
                # with eik=None would produce an edge that can never resolve, and
                # minting a synthetic key would fabricate an identity. Keep it as a
                # plain attribute instead — visible, but honestly outside the graph.
                if p["kind"] == "company" and not p["eik"]:
                    foreign_owners.append({"name": p["name"], "foreign_id": p["foreign_id"],
                                           "role": role})
                    continue
                rel = {
                    "kind": p["kind"], "name": p["name"],
                    "relation": relation, "role": role,
                    "direction": "in", "is_current": True,
                }
                if p["kind"] == "company":
                    rel["eik"] = p["eik"]
                else:
                    rel["person_key"] = self._key_for(p["name"])
                if p["share_bgn"] is not None:
                    rel["share_bgn"] = p["share_bgn"]
                related.append(rel)

        add(F_MANAGERS, "management", "Управител")
        add(F_PARTNERS, "ownership", "Съдружник")
        add(F_SOLE_OWNER, "ownership", "Едноличен собственик на капитала")

        activity = vals.get(F_ACTIVITY, "")
        return {
            "eik": eik,
            "name": vals.get(F_NAME),
            "legal_form": vals.get(F_FORM),
            "status": DEED_STATUS.get(deed.get("deedStatus")),
            "has_company_cases": bool(deed.get("hasCompanyCasees")),
            "address": vals.get(F_ADDRESS),
            "capital_eur": _capital_eur(vals.get(F_CAPITAL, "")),
            "founded_year": int(founded) if founded and founded.isdigit() else None,
            "activity": activity,
            # "проектиране" alone is not enough — it also covers designing electronics
            # (ЕИК 201407079 is a software/electronics firm that matched on it), so a
            # building-related word has to appear too.
            "is_construction": bool(
                re.search(r"строител|сград|жилищн|инженеринг", activity, re.I)
                or re.search(r"проектиран", activity, re.I)
                and re.search(r"сград|обект|строеж|жилищ", activity, re.I)
            ),
            "related": related,
            "foreign_owners": foreign_owners,
            "seizures": self._seizures(deed),
            "source": "registryagency",
            "source_site": "portal.registryagency.bg",
            "scope": self.scope,
        }

    # ---- depth-2: person -> every company they are attached to ----------

    def find_subjects(self, name: str) -> List[dict]:
        """Name -> candidate subjects. ``ident`` is an opaque server token.

        The register keys people on ЕГН and will not disclose it, so a name can
        legitimately return several *different* people. They are returned as-is;
        deciding whether two records are one human is not a call this scraper makes.
        """
        params = {"page": 1, "pageSize": 25, "count": 25, "name": name,
                  "selectedSearchFilter": 0, "includeHistory": "false"}
        resp = self.get(API_SUBJECTS, params=params, headers={"Accept": "application/json"})
        return [s for s in (resp.json() or []) if s.get("isPhysical")]

    def person_participations(self, subject: dict) -> dict:
        """One subject -> a ``person_participations`` record (papagal's shape)."""
        params = {"uid": subject["ident"], "name": subject["name"],
                  "searchInHistory": "false", "type": 1}
        resp = self.get(API_SUBJECT_FIELDS, params=params,
                        headers={"Accept": "application/json"})
        companies = []
        for row in resp.json() or []:
            relation, role = FIELD_ROLE.get(row.get("fieldName"), (None, None))
            if not relation:
                continue
            companies.append({
                "kind": "company",
                "eik": row.get("uic"),
                "name": (row.get("companyFullName") or "").replace('"', "").strip(),
                "relation": relation, "role": role,
                "share_pct": None,  # not exposed here; read the company's Deeds for shares
                "is_current": True,
            })
        return {
            "kind": "person_participations",
            "person_key": self._key_for(subject["name"]),
            "name": subject["name"],
            "companies": companies,
            "source": "registryagency",
            "source_site": "portal.registryagency.bg",
            "scope": self.scope,
        }

    def _scrape_persons(self) -> Iterator[dict]:
        for name in self.persons:
            try:
                subjects = self.find_subjects(name)
            except Exception as exc:  # noqa: BLE001
                self._log(f"{name}: subject search failed: {exc}")
                continue
            if not subjects:
                self._log(f"{name}: no subject found")
                continue
            if len(subjects) > 1:
                self._log(f"{name}: {len(subjects)} same-name subjects — kept separate")
            for subject in subjects:
                try:
                    yield self.person_participations(subject)
                except Exception as exc:  # noqa: BLE001
                    self._log(f"{name}: participations failed: {exc}")

    def scrape(self) -> Iterator[dict]:
        if self.persons:
            yield from self._scrape_persons()
            return
        yield from self._scrape_companies()

    def _scrape_companies(self) -> Iterator[dict]:
        for eik in self.eiks:
            url = (f"{API}/{eik}"
                   f"?entryDate=2100-01-01T00:00:00.000Z&loadFieldsFromAllLegalForms=false")
            try:
                resp = self.get(url, headers={"Accept": "application/json"})
                deed = resp.json()
            except Exception as exc:  # noqa: BLE001 - one bad ЕИК must not kill the run
                self._log(f"{eik} failed: {exc}")
                continue
            if not deed or not deed.get("uic"):
                self._log(f"{eik}: no deed returned")
                continue
            yield self._record(eik, deed)


SCRAPER = RegistryAgencyScraper


def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Търговски регистър ownership scraper (official; replaces papagal)")
    parser.add_argument("--eik", help="single ЕИК")
    parser.add_argument("--eiks-file", help="newline-separated ЕИК list")
    parser.add_argument("--persons-file",
                        help="depth-2: one person NAME per line — expand to every "
                             "company they manage or own")
    parser.add_argument("--person-key-map",
                        help="TSV 'name\\tperson_key' — reuse existing graph keys "
                             "instead of minting tr- ones (see module docstring)")
    args = parser.parse_args()

    if args.persons_file:
        with open(args.persons_file, encoding="utf-8") as fh:
            names = [ln.strip() for ln in fh if ln.strip()]
        key_map_p: Dict[str, str] = {}
        if args.person_key_map:
            with open(args.person_key_map, encoding="utf-8") as fh:
                for ln in fh:
                    parts = ln.rstrip("\n").split("\t")
                    if len(parts) >= 2 and parts[0].strip():
                        key_map_p[parts[0].strip()] = parts[1].strip()
        RegistryAgencyScraper("bg", persons=names, key_map=key_map_p).run()
        return

    eiks: List[str] = []
    if args.eik:
        eiks = [args.eik]
    elif args.eiks_file:
        with open(args.eiks_file, encoding="utf-8") as fh:
            eiks = [ln.strip() for ln in fh if ln.strip()]
    else:
        parser.error("provide --eik, --eiks-file, or --persons-file")

    key_map: Dict[str, str] = {}
    if args.person_key_map:
        with open(args.person_key_map, encoding="utf-8") as fh:
            for ln in fh:
                parts = ln.rstrip("\n").split("\t")
                if len(parts) >= 2 and parts[0].strip():
                    key_map[parts[0].strip()] = parts[1].strip()

    RegistryAgencyScraper("bg", eiks=eiks, key_map=key_map).run()


if __name__ == "__main__":
    _cli()
