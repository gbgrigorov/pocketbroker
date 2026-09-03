"""Parser tests for the Търговски регистър scraper.

Every case here is a real field value that broke the parser during the
2026-08-20 build. The register concatenates participants with no separator, so
the splitting is genuinely fiddly — keep these tests when touching it.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from crawlers.scraper_kit.sites.registryagency import (  # noqa: E402
    _capital_eur, _split_participants, person_key,
)


def test_mixed_case_people_with_shares():
    blob = ("Иван Петров Иванов, Държава: БЪЛГАРИЯ, Размер на дяловото участие: 2500.00 лв. "
            "Мария Георгиева Петрова, Държава: БЪЛГАРИЯ, Размер на дяловото участие: 1200.00 лв.")
    out = _split_participants(blob)
    assert [p["name"] for p in out] == ["Иван Петров Иванов", "Мария Георгиева Петрова"]
    assert [p["share_bgn"] for p in out] == [2500.0, 1200.0]
    assert all(p["kind"] == "person" for p in out)


def test_all_caps_name_is_not_split_mid_word():
    # Regression: an ALL-CAPS name used to split as "ДИМИТРИН" + "КА ВЛАДИМИРОВА
    # ПЕТРОВА", because every uppercase run looks like the start of a new name.
    blob = "МАРИЯ ГЕОРГИЕВА ПЕТРОВА, Държава: БЪЛГАРИЯ"
    out = _split_participants(blob)
    assert len(out) == 1
    assert out[0]["name"] == "МАРИЯ ГЕОРГИЕВА ПЕТРОВА"


def test_company_participants_are_captured_with_eik():
    # Regression: company partners were silently dropped, which is exactly the
    # edge an SPV chain is built from.
    blob = ('КАЛИСТРАТОВ ГРУП, ЕИК/ПИК 206422081, Държава: БЪЛГАРИЯ '
            '"ДЖИ ВИ ИНВЕСТ" ЕООД, ЕИК/ПИК 175044570, Държава: БЪЛГАРИЯ '
            'МАРИЯ ГЕОРГИЕВА ПЕТРОВА, Държава: БЪЛГАРИЯ')
    out = _split_participants(blob)
    assert [(p["kind"], p["eik"]) for p in out] == [
        ("company", "206422081"), ("company", "175044570"), ("person", None),
    ]
    assert out[1]["name"] == "ДЖИ ВИ ИНВЕСТ ЕООД"  # quotes stripped


def test_person_name_does_not_absorb_previous_country_value():
    # Regression: the person matched right after "Държава: БЪЛГАРИЯ" and swallowed it.
    blob = ('КАЛИСТРАТОВ ГРУП, ЕИК/ПИК 206422081, Държава: БЪЛГАРИЯ '
            'МАРИЯ ГЕОРГИЕВА ПЕТРОВА, Държава: БЪЛГАРИЯ')
    names = [p["name"] for p in _split_participants(blob)]
    assert "МАРИЯ ГЕОРГИЕВА ПЕТРОВА" in names
    assert not any(n.startswith("БЪЛГАРИЯ") for n in names)


def test_mixed_person_and_company_shares():
    blob = ('Георги Иванов Георгиев, Държава: БЪЛГАРИЯ, Размер на дяловото участие: 40.00 лв. '
            '"КАЛИСТРАТОВ ГРУП" АД, ЕИК/ПИК 206422081, Държава: БЪЛГАРИЯ, '
            'Размер на дяловото участие: 60.00 лв.')
    out = _split_participants(blob)
    assert out[0]["kind"] == "person" and out[0]["share_bgn"] == 40.0
    assert out[1]["kind"] == "company" and out[1]["share_bgn"] == 60.0


def test_deleted_circumstance_yields_nothing():
    # The register writes this instead of blanking a field that no longer applies.
    assert _split_participants("Заличено обстоятелство.") == []
    assert _split_participants("") == []


def test_capital_parses_euro_and_leva():
    assert _capital_eur("2556.46 €") == 2556.46
    assert _capital_eur("5000.00 лв") == 2556.46  # converted at the peg
    assert _capital_eur("") is None


def test_person_key_is_deterministic_and_namespaced():
    a = person_key("Георги Иванов Георгиев")
    assert a == person_key("  георги иванов георгиев  ")  # normalised
    assert a.startswith("tr-")  # never collides with a papagal hash
    assert a != person_key("Иван Петров Иванов")


def test_foreign_owner_is_captured_as_a_company():
    """A foreign parent carries a home-register id, not an ЕИК. This used to fail
    the whole entry match, so any company owned from abroad looked ownerless —
    exactly the "who really owns this" question the product exists to answer.
    Seen on ЕИК 205890369 (owned by a German SE)."""
    blob = ("Б2Б МЕДИЯ ХОЛДИНГ СЕ, Идентификация HRB 34711, "
            "Чуждестранно юридическо лице, Държава: ГЕРМАНИЯ")
    out = _split_participants(blob)
    assert len(out) == 1
    assert out[0]["kind"] == "company"
    assert out[0]["name"] == "Б2Б МЕДИЯ ХОЛДИНГ СЕ"   # the digit must survive
    assert out[0]["foreign_id"] == "HRB 34711"
    assert out[0]["eik"] is None


def test_foreign_manager_is_still_a_person():
    blob = "Тодор Асенов Тодоров, Държава: БЪЛГАРИЯ Ханс Мюлер, Държава: ГЕРМАНИЯ"
    out = _split_participants(blob)
    assert [p["name"] for p in out] == ["Тодор Асенов Тодоров", "Ханс Мюлер"]
    assert all(p["kind"] == "person" for p in out)


def test_designing_electronics_is_not_construction():
    """`проектиране` alone over-matched: ЕИК 201407079 designs electronics and
    software and was classified as a builder purely on that word."""
    import re
    from crawlers.scraper_kit.sites.registryagency import RegistryAgencyScraper  # noqa: F401

    def is_construction(activity: str) -> bool:
        return bool(
            re.search(r"строител|сград|жилищн|инженеринг", activity, re.I)
            or re.search(r"проектиран", activity, re.I)
            and re.search(r"сград|обект|строеж|жилищ", activity, re.I)
        )

    electronics = ("КОНСУЛТАНТСКИ, МАРКЕТИНГОВИ, ИНФОРМАЦИОННИ И РЕКЛАМНИ УСЛУГИ; "
                   "ПРОЕКТИРАНЕ, ПРОИЗВОДСТВО, МОНТАЖ И ПОДДРЪЖКА НА ЕЛЕКТРОННИ ИЗДЕЛИЯ")
    builder = ("Осъществяване на технологично проектиране, строителство и реконструкция "
               "на къщи, жилищни, административни, търговски и промишлени сгради")
    assert is_construction(electronics) is False
    assert is_construction(builder) is True
