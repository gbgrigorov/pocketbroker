"""Matcher tests — the one piece of pure logic worth pinning down.

The risk we guard against is a false positive (wrongly flagging a builder), so
the negative cases matter as much as the positive ones.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from crawlers.signals.match import Target, distinctive_terms, find_mentions, index_targets


def test_company_distinctive_terms_drops_generic_words():
    assert distinctive_terms("АРТЕКС ИНЖЕНЕРИНГ АД", "company") == ["артекс"]
    # an all-generic name yields nothing distinctive (won't match on "строй")
    assert distinctive_terms("СТРОЙ ИНВЕСТ ГРУП ООД", "company") == []


def test_person_terms_require_full_name():
    assert distinctive_terms("Стефан Стефанов", "person") == ["стефан стефанов"]
    assert distinctive_terms("Иван", "person") == []  # bare first name -> no term


def test_company_whole_word_match_is_high_confidence():
    text = "Внимавайте с АРТЕКС, недостроена сграда от години."
    targets = [Target(name="АРТЕКС ИНЖЕНЕРИНГ АД", kind="company", eik="831641791")]
    hits = find_mentions(text, targets)
    assert len(hits) == 1
    assert hits[0].confidence == "fuzzy_high"
    assert "артекс" in hits[0].snippet


def test_no_false_positive_on_generic_word():
    text = "Търся надеждна строй фирма за ремонт."
    targets = [Target(name="СТРОЙ ИНВЕСТ ГРУП ООД", kind="company")]
    assert find_mentions(text, targets) == []


def test_index_targets_prunes_tokens_shared_by_many_companies():
    # "проект" is shared by many companies -> not distinctive -> pruned away.
    companies = [
        Target(name="Т-Проект", kind="company"),
        Target(name="КА ПРОЕКТ", kind="company"),
        Target(name="ЕКО КОНСУЛТ ПРОЕКТ", kind="company"),
        Target(name="ХСС ПРОЕКТ КОНСУЛТ", kind="company"),
        Target(name="АРТЕКС ИНЖЕНЕРИНГ АД", kind="company"),
    ]
    index_targets(companies, max_company_df=2)
    by_name = {t.name: t for t in companies}
    assert "проект" not in by_name["Т-Проект"].terms()      # pruned -> no terms left
    assert by_name["Т-Проект"].terms() == []
    assert by_name["АРТЕКС ИНЖЕНЕРИНГ АД"].terms() == ["артекс"]  # unique -> kept

    text = "Имам лош опит с този проект, голям проект, ужасен проект."
    assert find_mentions(text, companies) == []  # nobody flagged on the word "проект"


def test_no_false_positive_on_komers_suffix():
    # Real regression: a Nova Build complaint mentioning the unrelated
    # "Ево Билд Комерс ООД" must NOT flag "МОНОЛИТСТРОЙ КОМЕРС". With several
    # "монолитстрой" namesakes the brand token is pruned; the company must not
    # then fall back to the generic word "комерс".
    companies = [
        Target(name="МОНОЛИТСТРОЙ КОМЕРС", kind="company"),
        Target(name="МОНОЛИТСТРОЙ ИНЖЕНЕРИНГ", kind="company"),
        Target(name="МОНОЛИТСТРОЙ ГРУП", kind="company"),
    ]
    index_targets(companies, max_company_df=2)  # "монолитстрой" shared by 3 -> pruned
    by_name = {t.name: t for t in companies}
    assert by_name["МОНОЛИТСТРОЙ КОМЕРС"].terms() == []  # "комерс" is now a stopword
    text = "Нова Билд са мошеници. За пълна информация вижте Ево Билд Комерс ООД."
    assert find_mentions(text, companies) == []


def test_no_false_positive_on_energy_construction_suffixes():
    # Real regression: a complaint about "енерджи хаус 99" must NOT flag
    # "Еко Енерджи Кънстракшън" via the generic words "енерджи"/"кънстракшън".
    targets = [Target(name="Еко Енерджи Кънстракшън", kind="company")]
    assert distinctive_terms("Еко Енерджи Кънстракшън", "company") == []
    text = "вкарвам в черния списък и фирма енерджи хаус 99 на борислав илиев"
    assert find_mentions(text, targets) == []


def test_person_full_name_matches_but_bare_first_name_does_not():
    text = "Управителят Стефан Стефанов изчезна с парите."
    assert len(find_mentions(text, [Target(name="Стефан Стефанов", kind="person")])) == 1
    # A different person sharing only the first name must NOT match.
    assert find_mentions(text, [Target(name="Величко Петров", kind="person")]) == []
