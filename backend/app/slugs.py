"""Cyrillic -> Latin slug generation for SEO-friendly entity URLs.

Mirrors the transliteration table in crawlers/scraper_kit/sites/novitesgradi.py
(used there for matching neighbourhood slugs). Keep the two tables in sync —
duplicated rather than imported because backend/ and crawlers/ are independent
top-level packages with no existing cross-import relationship.
"""

from __future__ import annotations

import re

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "zh", "з": "z",
    "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p",
    "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "sht", "ъ": "a", "ь": "y", "ю": "yu", "я": "ya",
}


def transliterate(text: str) -> str:
    return "".join(_TRANSLIT.get(ch, ch) for ch in (text or "").lower())


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", transliterate(text)).strip("-")
