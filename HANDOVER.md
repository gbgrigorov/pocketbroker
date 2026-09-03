# BG Real Estate Intelligence Platform — Handover

<!--
MAINTENANCE RULE — CURRENT-STATE snapshot, NOT an append-only log. Scope = today / last session.
• Remove a task the moment it's done. • Never leave contradictory entries. • Keep only live
status + a one-line pointer to where detail lives. Prune regularly — if it's growing, it's wrong.
-->

## Active / in-flight
<!-- one line per in-flight task; delete when done -->
- **Papagal dead → ТР scraper live.** papagal.bg is Cloudflare-blocked (2026-08-20);
  `crawlers/scraper_kit/sites/registryagency.py` replaces it (official ТР JSON API, no
  CAPTCHA). Follow-ups: back-fill `activity`/`запор` for the ~750 papagal-sourced
  companies; reconcile `tr-` person keys against papagal hashes; parser can't split two
  people sharing one `Държава:` (ЕИК 120564924).
- **Research sync API — deployed, needs 2 manual prod steps.** MacBook↔prod push
  API (`/api/admin/sync/*`, `scripts/pb.py`) is live in code but **inert until**
  the VPS gets (1) the nginx `^~ /api/admin/sync` deny block and (2)
  `RESEARCH_API_TOKEN` in `/home/deploy/secrets/pocketbroker.env`. In that order.
  Hand the VPS agent `deploy/SYNC_API_DEPLOY.md`. Then retrieve the token to the
  local `.env` and smoke-test `python3 scripts/pb.py requests`.
  `deploy/ENTITY_PUSH.md` is now DEPRECATED — running it would erase API-written
  findings.
- **New-buildings crawl:** novitesgradi.bg scraper committed (5 Sofia developments). Pending:
  confirm DB rows (`cd backend && .venv/bin/python -m etl.run_phase3`); `developer_id` null on
  all 5 + 2 unresolved neighbourhood slugs (easy follow-ups); expand coverage via район/квартал
  pages (luximmo.bg viable, not built). Detail → `docs/NEW_BUILDINGS_CRAWL_REPORT_2026-06-01.md`.
  Delete throwaway `data/fixtures/.../_*.py` probe scripts. Network needs `dangerouslyDisableSandbox`.

## Done last session (2026-06-02) — prune when stale
- **Signals / official-records + Component B insolvency — committed** (`feat/new-building-projects`,
  not pushed). Full write-up = the Outcome section of
  `docs/superpowers/plans/2026-06-02-official-records-check.md`. One-liner: Златен век court saga
  is under SPV „Артекс Златен век" ООД `175376051` (not the parent); 97-company Артекс group
  mapped; curated official records + conservative sibling→builder propagation; insolvency flag
  from Papagal status. Memories: `court-cases-hide-in-spvs`, `official-records-check-findings`.
