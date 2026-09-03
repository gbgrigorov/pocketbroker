"""Name matcher — decide which developer/person a free-text source is about.

The forum and web layers produce unstructured text; this module finds mentions
of known targets (companies + their owners/managers) in that text and grades how
confident the match is. It is deliberately conservative: a false "this builder
is a fraud" flag is worse than a miss, so person matches require a full name and
generic company words ("строй", "груп", "инженеринг") never match on their own.

Confidence levels (mirrors ``entity_signal.match_confidence``):
    fuzzy_high : a distinctive whole-word company token, or a full person name
    fuzzy_low  : a distinctive token only as a substring (weaker)

``eik`` confidence is reserved for the registry layer, which keys on ЕИК and
never goes through this text matcher.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional

# Generic / common words that are NOT distinctive on their own. Covers legal
# forms, construction jargon, and frequent Bulgarian dictionary words that
# otherwise produce false "mentions" when they happen to be a company's only
# distinctive token (вариант, дизайн, продукт, хоум…).
_STOPWORDS = {
    # legal forms (abbreviated + spelled out)
    "оод", "еоод", "ад", "еад", "ет", "кд", "сд", "ltd", "ood", "eood", "ad", "ead",
    "еднолично", "дружество", "ограничена", "отговорност", "акционерно", "събирателно",
    "командитно", "сдружение",
    # construction / business jargon
    "строй", "строи", "строеж", "строежи", "строителство", "строителна", "строителни",
    "строител", "стройинвест", "инженеринг", "инвест", "инвестмънт", "груп", "груп",
    "холдинг", "девелопмънт", "дивелопмънт", "къмпани", "компания", "компани", "консулт",
    "пропърти", "пропъртис", "проект", "проекти", "дизайн", "design", "билдинг", "билд",
    "build", "building", "хаус", "house", "хоум", "home", "резиденс", "residence", "сити",
    "city", "груп", "group", "invest", "development", "holding", "company", "estate",
    "real", "парк", "park", "плаза", "център", "център", "център", "продукт", "продукция",
    "трейд", "транс", "мулти", "multi", "актив", "active", "бизнес", "business", "вижън",
    "комерс", "comers", "commerce", "енерджи", "energy", "кънстракшън", "кънстракшан",
    "construction",
    "vision", "грийн", "green", "лайф", "life", "вариант", "стандарт", "комфорт", "престиж",
    # frequent dictionary words seen as company tokens
    "добро", "някой", "непознат", "направи", "фондация", "медицински", "здраве", "шанс",
    "база", "нова", "ново", "нови", "ауто", "комплекс", "сграда", "дом", "къща",
    "монолит", "монолитна", "монолитно", "такси", "декор", "хит", "ресурс", "софия",
    # glue words
    "и", "на", "за", "от", "ко", "виж",
}


def normalize(text: Optional[str]) -> str:
    """Lowercase, drop quotes/punctuation noise, collapse whitespace."""
    if not text:
        return ""
    text = re.sub(r"[\"'„“”«».,;:!?()\[\]/\\-]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def distinctive_terms(name: str, kind: str) -> List[str]:
    """Tokens worth searching for in free text.

    company : distinctive (non-stopword) tokens >= 4 chars, e.g.
              "АРТЕКС ИНЖЕНЕРИНГ АД" -> ["артекс"]
    person  : the full name kept as a phrase (matched whole, not per-token), so
              we return a single multi-word term, e.g. ["стефан стефанов"].
    """
    norm = normalize(name)
    if not norm:
        return []
    tokens = [t for t in norm.split() if t not in _STOPWORDS]
    if kind == "person":
        # Keep the full personal name (>= 2 tokens) as one phrase.
        return [" ".join(tokens)] if len(tokens) >= 2 else []
    return [t for t in tokens if len(t) >= 4]


@dataclass
class Target:
    """A developer or a person we want to find mentions of."""

    name: str
    kind: str  # 'company' | 'person'
    eik: Optional[str] = None
    person_key: Optional[str] = None
    entity_id: Optional[int] = None
    override_terms: Optional[List[str]] = None  # set by :func:`index_targets`

    def terms(self) -> List[str]:
        if self.override_terms is not None:
            return self.override_terms
        return distinctive_terms(self.name, self.kind)


def index_targets(targets: List["Target"], max_company_df: int = 2) -> List["Target"]:
    """Prune non-distinctive company tokens using their frequency across targets.

    A token that appears in the names of *many* companies (``проект``,
    ``българия``, ``билдинг``, ``сити``…) carries no identifying power, so we
    drop it. Tokens shared by more than ``max_company_df`` companies are removed;
    a company left with no distinctive token simply won't be matched (we'd rather
    miss it than flag the wrong builder). Person targets are untouched.

    Returns the same list (targets mutated in place with ``override_terms``).
    """
    from collections import Counter

    df: Counter = Counter()
    company_terms = {}
    for t in targets:
        if t.kind != "company":
            continue
        toks = set(distinctive_terms(t.name, "company"))
        company_terms[id(t)] = toks
        for tok in toks:
            df[tok] += 1
    common = {tok for tok, n in df.items() if n > max_company_df}
    for t in targets:
        if t.kind == "company":
            t.override_terms = [tok for tok in distinctive_terms(t.name, "company")
                                if tok not in common]
    return targets


@dataclass
class Mention:
    target: Target
    confidence: str  # 'fuzzy_high' | 'fuzzy_low'
    snippet: str


def _snippet(text: str, idx: int, span: int = 200) -> str:
    start = max(0, idx - span // 2)
    end = min(len(text), idx + span // 2)
    s = text[start:end].strip()
    return ("…" + s if start > 0 else s) + ("…" if end < len(text) else "")


def _whole_word(term: str, text: str) -> int:
    """Index of a whole-word/phrase match of ``term`` in ``text``, else -1."""
    m = re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text)
    return m.start() if m else -1


def find_mentions(text: str, targets: Iterable[Target]) -> List[Mention]:
    """Return one conservative :class:`Mention` per target present in ``text``.

    A false positive (wrongly flagging a builder) is the costly error, so the
    bar is high — many BG company names embed dictionary words (``шанс``,
    ``база``, ``нова``) that occur in ordinary text:

    - **person**  : full name phrase must appear (fuzzy_high).
    - **company, multi-token name** : >= 2 distinct distinctive tokens must
      appear as whole words (fuzzy_high) — one shared dictionary word is not
      enough.
    - **company, single-token name** : that token must appear whole-word AND be
      >= 5 chars (fuzzy_high); shorter single tokens are too risky and dropped.

    Substring-only matches are not emitted.
    """
    norm_text = normalize(text)
    if not norm_text:
        return []
    out: List[Mention] = []
    for target in targets:
        terms = target.terms()
        if not terms:
            continue
        if target.kind == "person":
            idx = _whole_word(terms[0], norm_text)
            if idx != -1:
                out.append(Mention(target, "fuzzy_high", _snippet(norm_text, idx)))
            continue
        # company
        hits = [(t, _whole_word(t, norm_text)) for t in terms]
        present = [(t, i) for t, i in hits if i != -1]
        if len(terms) >= 2:
            if len(present) >= 2:
                out.append(Mention(target, "fuzzy_high", _snippet(norm_text, present[0][1])))
        else:  # single distinctive token — needs to be long to be safe
            t, i = hits[0]
            if i != -1 and len(t) >= 6:
                out.append(Mention(target, "fuzzy_high", _snippet(norm_text, i)))
    return out
