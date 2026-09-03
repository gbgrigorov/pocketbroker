"""Reusable, multi-city scraping framework for the BG Real Estate Intelligence Platform.

Three stages, each city-parameterized and idempotent (safe to re-run):

    fetch+parse (per site)  ->  normalize/merge  ->  load (ETL)

- ``base.BaseScraper``  — one subclass per website (in ``sites/``); handles fetching,
  rate-limiting, encoding, retries and per-run telemetry, then dumps raw JSONL.
- ``cities``            — registry of cities + per-site URL params (multi-city by design).
- ``run``              — CLI orchestrator that dispatches scrapers by domain/site/city.
- ``stats``            — rolls per-run telemetry into a single headline counter.

Scrapers run under the system ``python3`` (httpx + beautifulsoup4 available); the
normalizers and ETL run under ``backend/.venv``.
"""
