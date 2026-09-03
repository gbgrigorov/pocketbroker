# SEO / URL Migration — Handover

Migration from hash-based SPA routing (`/#/...`) to real URL paths, plus the
Google Analytics and SEO work that depends on it. This document explains what
changed and, most importantly, **how nginx must behave** for it to work in
production. The one outstanding manual step is the nginx change described below.

## Why this happened

Google Analytics only ever saw the homepage, and Google could not index any
inner page. Both problems had the same root cause: the whole site lived behind
the URL fragment (`#`). Everything after `#` is invisible to the server and to
search-engine crawlers — to a browser, `/#/e/123` and `/#/about` are the *same*
URL (`/`), just with a different fragment. So GA recorded one pageview and
Google saw one page.

The fix was to move to real paths (e.g. `/about`, `/c/sofia/n/lozenets`,
`/e/175354619/em-vi-ef-holding`) that the server and crawlers can see.

## What changed in the app

- **Routing** now uses the browser History API and real paths instead of `#`
  fragments. Old `#/...` bookmarks still work — on load they are silently
  rewritten to the equivalent path.
- **Google Analytics** fires a fresh pageview on every in-app navigation, not
  just the first load, so each page is now counted.
- **Internal links** are real `<a href="...">` anchors. Crawlers can follow
  them, and Ctrl/Cmd-click opens them in a new tab like any normal link.
- **Per-page metadata**: each page sets its own title, meta description, and
  canonical URL, so search results and social shares are page-specific rather
  than all showing the homepage text.
- **Entity URLs include a name slug** for readability and SEO
  (`/e/175354619/em-vi-ef-holding`). The slug is cosmetic only — the ЕИК (or
  person key) remains the real lookup key, so a wrong or missing slug still
  resolves to the right entity.
- **`robots.txt`** is shipped with the frontend and points crawlers at the
  sitemap.
- **`sitemap.xml`** is generated at deploy time from the database and written
  into the web root. It lists every static page, every city and neighbourhood,
  and every company profile. People are deliberately excluded from the sitemap
  for privacy.

## How nginx must function

> **Status:** already satisfied on the live server — no nginx edit is needed.
> The `location /` block already uses `try_files $uri $uri/ /index.html;`
> (it served the old hash router and is identical to what History mode needs).
> The text below explains *why* that rule is required. The one real
> outstanding step is a deploy to generate `sitemap.xml` — see "State" below.

This is the rule the new URLs depend on, and it is **required** — without it,
the new paths would break on direct load or refresh.

The frontend is a single-page application. The only HTML file that physically
exists in the web root is `index.html`. All the "pages" (`/about`,
`/c/sofia/...`, `/e/...`, etc.) are constructed in the browser by JavaScript
*after* `index.html` loads. There is no `/about/index.html` on disk and never
will be.

So nginx needs one rule for the site root: **when a requested path matches a
real file, serve that file; otherwise serve `index.html`.**

That single rule produces the correct behaviour for every case:

- **Real static files** — `index.html`, the hashed JS/CSS bundles, the
  favicon, `robots.txt`, `sitemap.xml`, images — match a file on disk and are
  served directly. This is why `robots.txt` and `sitemap.xml` must be checked
  *before* the fallback: they are real files and must be returned as-is, not
  replaced by the app shell.
- **App routes** — `/about`, `/c/sofia/n/lozenets`, `/e/123/some-company`,
  `/e/123/.../network`, and anything else the router understands — do **not**
  match a file on disk, so nginx falls back to `index.html`. The browser loads
  the app, the router reads the URL, and renders the right page. This is what
  makes a direct visit, a refresh, or a shared deep link work instead of
  returning 404.

Two boundaries to respect:

- **Do not apply the fallback to the API.** Requests under `/api/` are proxied
  to the backend and must keep their real status codes — a missing API resource
  has to stay a 404, not be masked by the app shell. Only the site root
  (the block serving the static frontend) gets the fallback.
- **Order matters.** The real-file check comes first, the `index.html` fallback
  last. If the fallback were checked first, requests for `sitemap.xml` or the
  JS bundles would be answered with HTML and the site would break.

The concrete config snippet and verification steps live in
[`SETUP.md`](SETUP.md) §5a. In short, the root location uses
`try_files $uri $uri/ /index.html;` — "try the file, then the directory, then
fall back to the app shell."

## State / what's left

- App code, the GA fix, slugs + migration, links, per-page metadata,
  `robots.txt`, and the sitemap generator are done and on `main`; the frontend
  builds clean and the backend tests pass.
- The nginx History-mode fallback is **already live** — verified: deep links
  (`/e/...`), `/about`, and `robots.txt` all return 200, and `/api/*` misses
  still return real 404s.
- **Outstanding:** run a deploy. `sitemap.xml` is generated into the web root
  at deploy time and does not yet exist on disk, so `/sitemap.xml` currently
  falls back to `index.html` (served as `text/html`) — and `robots.txt`
  already points crawlers at it. A deploy materialises the real file; no nginx
  change is involved.
