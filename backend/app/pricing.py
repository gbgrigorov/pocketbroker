"""Court / deep-research order pricing — the single source of truth.

Order-capture only: these are the quotes we store and show; no online payment runs
here. The frontend mirrors these numbers in ``frontend/src/lib/researchPricing.js``
for live estimates, but the server price (computed here) is always authoritative.

Model (see the approved plan):
  * single company, by EIK            -> €1
  * single company, by EIK + Name     -> 3× = €3   (fuzzier results)
  * whole network, by EIK             -> ceil(companies / 10) × €3
  * whole network, by EIK + Name      -> 3× the block total
Only companies with an EIK are ever counted (persons have none).
"""

from __future__ import annotations

import math

COURT_SINGLE_EUR = 1.00       # single company, by EIK
NETWORK_BLOCK_EUR = 3.00      # per started block of companies (network scope)
BLOCK_SIZE = 10               # companies per block
NAME_MULTIPLIER = 3           # EIK + Name premium (fuzzier results)

SEARCH_TYPES = ("eik", "eik_name")


def _mult(search_type: str) -> int:
    return NAME_MULTIPLIER if search_type == "eik_name" else 1


def quote_single(search_type: str) -> float:
    """Price for a court check on a single company."""
    return round(COURT_SINGLE_EUR * _mult(search_type), 2)


def quote_network(company_count: int, search_type: str) -> float:
    """Price for a court check across a whole network of ``company_count`` companies."""
    blocks = math.ceil(company_count / BLOCK_SIZE) if company_count > 0 else 0
    return round(blocks * NETWORK_BLOCK_EUR * _mult(search_type), 2)


def quote(scope: str, company_count: int, search_type: str) -> float:
    """Dispatch on scope: ``company`` -> single, ``network`` -> block pricing."""
    if scope == "network":
        return quote_network(company_count, search_type)
    return quote_single(search_type)
