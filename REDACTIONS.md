# About this mirror

This is a **redacted, shareable copy** of a private working repository. The code,
architecture, data pipeline and tests are intact. What was removed or replaced is
listed below, so nothing here is silently misleading.

The platform researches Bulgarian property developers against public registers
(Търговски регистър, the national court-acts portal). That research necessarily
touches named private individuals, so the outputs — not the machinery — are what
had to come out.

## Removed entirely

| What | Why |
|---|---|
| `docs/*_RESEARCH_FINDINGS.md` (12 files) | Completed dossiers on real companies naming private individuals, their ownership networks and litigation history. |
| `docs/MONOLITSTROY_CASE_STUDY.md` | Same. |
| `docs/ADMIN_REQUESTS_BULK_2026-08-04.md` | Bulk research run over 35 real user-submitted requests. |
| `docs/EMAIL_TEMPLATES.md`, `docs/ktg_report.html` | Personal contact details / a rendered dossier naming individuals. |
| `data/bundles/*.json` | Research payloads: 51 entities, 31 of them named natural persons, plus court-check results. |
| `frontend/src/reports/aks-kepital.js`, `.../aleksandar-inzhenering.js` | Client-facing AI dossiers on two real companies, marked ПОВЕРИТЕЛНО. |

## Replaced

- **`frontend/src/reports/demo-stroy.js`** — a new, entirely fictional report module
  with the identical data shape, so the report feature still runs and its contract
  stays documented. Every ЕИК, company and person in it is invented.
- **Personal names in tests, fixtures, SQL comments and docs** — real individuals
  encountered during research were used as test data. All replaced with fictional
  names, consistently, so assertions still hold. Company names (public legal
  entities, on the public register) were left as-is.
- **Deployment identifiers** — the production hostname is `app.example.com`, the
  deploy user is `deploy`, and the live analytics measurement ID was dropped.
  No credentials were ever committed to this project; `.env` has always been ignored.

## Not included

- `crawlers/scraper_kit/tests/fixtures/` — saved real register pages (personal data).
  The tests that need them **skip** rather than fail; the rest of the suite runs.
- The private scraped datasets under `data/raw/ownership/`, `data/raw/builders/`,
  `data/raw/signals/` and all database dumps. These have always been gitignored.

Public market data (imot.bg price history for four cities, air quality, transport,
new-building listings) is included in full.

## Running the tests

`crawlers/` tests are stdlib-only and pass as shipped. `backend/` tests need
`pytest` + the backend dependencies; they were not executed while preparing this
mirror.
