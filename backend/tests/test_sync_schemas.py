"""Bundle validation. Structural rules fail loudly here, before any DB work."""

import pytest
from pydantic import ValidationError

from app.sync.schemas import Bundle


def test_empty_bundle_is_valid():
    b = Bundle()
    assert b.entities == [] and b.edges == [] and b.builder is None


def test_company_entity_requires_eik():
    with pytest.raises(ValidationError, match="eik"):
        Bundle(entities=[{"kind": "company", "name": "Артекс ООД"}])


def test_person_entity_requires_person_key():
    # A keyless person would create a duplicate node on every re-push, and a
    # fuzzy name fallback could merge two different people. Fail instead.
    with pytest.raises(ValidationError, match="person_key"):
        Bundle(entities=[{"kind": "person", "name": "Иван Иванов"}])


def test_edge_ref_needs_exactly_one_key():
    with pytest.raises(ValidationError, match="eik"):
        Bundle(edges=[{"src": {}, "dst": {"eik": "111"}, "relation": "ownership"}])


def test_full_bundle_parses():
    b = Bundle(**{
        "entities": [
            {"kind": "company", "eik": "175376051", "name": "Артекс Златен век ООД",
             "legal_form": "ООД", "capital_eur": 5000, "founded_year": 2008,
             "source": "papagal"},
            {"kind": "person", "person_key": "175376051-2", "name": "Иван Иванов"},
        ],
        "builder": {"eik": "175376051", "name": "Артекс Златен век ООД",
                    "insolvency_flag": False},
        "edges": [{"src": {"person_key": "175376051-2"}, "dst": {"eik": "175376051"},
                   "relation": "ownership", "share_pct": 50,
                   "valid_from": "2008-01-01"}],
        "signals": [{"subject_kind": "company", "matched_name": "Артекс Златен век ООД",
                     "matched_eik": "175376051", "source_type": "registry",
                     "tier": "official", "match_confidence": "eik",
                     "url": "https://legalacts.justice.bg/Search/GetAct?actId=123"}],
        "court_checks": [{"eik": "175376051", "method": "eik", "acts_found": 3,
                          "checked_at": "2026-08-20T10:00:00"}],
        "report_md": "# Findings",
        "notes": "internal",
    })
    assert b.entities[0].capital_eur == 5000
    assert b.edges[0].src.person_key == "175376051-2"
    assert b.court_checks[0].acts_found == 3
