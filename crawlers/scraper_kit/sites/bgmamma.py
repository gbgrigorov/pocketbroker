"""BG-Mamma forum scraper — the community-signal corpus for bad builders.

BG-Mamma (SMF-derived forum) hosts long-running threads where owners name and
shame construction firms. We pull the post text + permalink + date from a small
set of high-signal threads; a later matching step (``backend/etl/load_signals``)
decides which known developer/person each post is about.

We store only post text + a link back to the original — never a re-publication —
and rate-limit politely via :class:`BaseScraper`.

Threads (Sofia / national, real-estate "black list" + complaints):
    1131192  Некоректни строители / Черен списък
    530948   Незавършени строежи от строители измамници
    1248083  Мнение относно строителни фирми/инвеститори

    python3 -m crawlers.scraper_kit.sites.bgmamma            # default threads
    python3 -m crawlers.scraper_kit.sites.bgmamma --max-pages 20
"""

from __future__ import annotations

import re
from typing import Iterator, List

from crawlers.scraper_kit.base import BaseScraper

BASE = "https://www.bg-mamma.com/?topic={topic}.{offset}"
POSTS_PER_PAGE = 15

DEFAULT_THREADS: List[str] = ["1131192", "530948", "1248083"]


class BgMammaScraper(BaseScraper):
    site = "bgmamma"
    domain = "signals"
    rate_limit_s = 1.5  # be polite to a community forum

    def __init__(self, scope: str = "sofia", threads: List[str] | None = None,
                 max_pages: int = 30):
        super().__init__(scope)
        self.threads = threads or DEFAULT_THREADS
        self.max_pages = max_pages

    def _page_count(self, soup, topic: str) -> int:
        """Largest paginated offset on the page → number of pages (capped)."""
        offsets = [int(m) for m in re.findall(rf"\?topic={topic}\.(\d+)", str(soup))]
        max_off = max(offsets) if offsets else 0
        pages = max_off // POSTS_PER_PAGE + 1
        return min(pages, self.max_pages)

    def _parse_page(self, soup, topic: str) -> Iterator[dict]:
        for post in soup.select("div.topic-post"):
            body = post.select_one(".post-content")
            if body is None:
                continue
            text = body.get_text(" ", strip=True)
            if len(text) < 20:  # skip empty / structural posts
                continue
            link_el = post.select_one("a.post-link[href]")
            date_el = post.select_one(".post-date")
            author_el = post.select_one(".post-user-name")
            # Stable, unique permalink: prefer the real post-link, else build one
            # from the post's msg id (so every post has a distinct url).
            msg_el = post.select_one("[data-msg]")
            msg_id = msg_el["data-msg"] if msg_el else None
            url = (link_el["href"] if link_el and link_el.get("href")
                   else f"https://bg-mam.ma/p/{topic}/{msg_id}" if msg_id
                   else BASE.format(topic=topic, offset=0))
            yield {
                "thread": topic,
                "url": url,
                "post_date": date_el.get_text(strip=True) if date_el else None,
                "author": author_el.get_text(strip=True) if author_el else None,
                "text": text,
            }

    def scrape(self) -> Iterator[dict]:
        for topic in self.threads:
            first = self.soup(BASE.format(topic=topic, offset=0))
            pages = self._page_count(first, topic)
            self._log(f"thread {topic}: {pages} pages")
            yield from self._parse_page(first, topic)
            for page in range(1, pages):
                offset = page * POSTS_PER_PAGE
                try:
                    soup = self.soup(BASE.format(topic=topic, offset=offset))
                except Exception as exc:  # noqa: BLE001
                    self.stats.errors += 1
                    self._log(f"thread {topic} offset {offset} failed: {exc}")
                    continue
                yield from self._parse_page(soup, topic)


SCRAPER = BgMammaScraper


def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="BG-Mamma builder-complaint scraper")
    parser.add_argument("--max-pages", type=int, default=30)
    parser.add_argument("--threads", nargs="*", help="override topic ids")
    args = parser.parse_args()
    BgMammaScraper(threads=args.threads, max_pages=args.max_pages).run()


if __name__ == "__main__":
    _cli()
