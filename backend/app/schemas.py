"""Pydantic schemas for the auth endpoints (fastapi-users read/create/update)
plus the public "order a research" lead-capture form.

The auth schemas just extend the library's base schemas with our extra
``name``/``tier`` fields so the API returns and accepts them.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal, Optional

from fastapi_users import schemas
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserRead(schemas.BaseUser[int]):
    name: Optional[str] = None
    tier: str = "member"


class UserCreate(schemas.BaseUserCreate):
    name: Optional[str] = None


class UserUpdate(schemas.BaseUserUpdate):
    name: Optional[str] = None


# --- "Order a research" lead capture -----------------------------------------

# Whitelist sanitiser for the free-text fields: keep letters (Unicode-aware, so
# Cyrillic passes), digits, spaces, and a small set of punctuation real company
# names use. Everything else — control bytes, null bytes, and injection/markup
# characters like < > ; \ { } | $ ` — is dropped. Defence-in-depth on top of the
# ORM (SQL-safe) and Vue escaping (XSS-safe).
_ALLOWED_PUNCT = set(" .,&-'()/№")


def clean_text(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    cleaned = "".join(c for c in s if c.isalnum() or c in _ALLOWED_PUNCT)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


class ResearchRequestCreate(BaseModel):
    # Reject unexpected fields outright and trim surrounding whitespace.
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    company_name: str = Field(min_length=1, max_length=200)
    requester_email: EmailStr
    company_eik: Optional[str] = Field(default=None, pattern=r"^(\d{9}|\d{13})$")
    owner: Optional[str] = Field(default=None, max_length=200)
    requester_name: Optional[str] = Field(default=None, max_length=120)
    details: Optional[str] = Field(default=None, max_length=2000)
    search_query: Optional[str] = Field(default=None, max_length=200)

    # Pay-to-expedite: when true we run this single company ASAP instead of the
    # ~1/day queue, at the per-company court price (server-computed — see app.pricing).
    # ``search_type`` defaults to name-only pricing when no EIK was provided.
    expedited: bool = False
    search_type: Optional[Literal["eik", "eik_name"]] = None

    # CAPTCHA (server-verified) + honeypot. ``website`` must stay empty: max_length=0
    # means any value a bot fills in trips a 422 before we ever touch the DB.
    captcha_answer: int
    captcha_exp: int
    captcha_sig: str = Field(max_length=128)
    website: Optional[str] = Field(default=None, max_length=0)

    # Sanitise the free-text fields *before* the length limits above are checked,
    # so only clean text is validated and stored.
    @field_validator("company_name", "owner", "requester_name", "details",
                     "search_query", mode="before")
    @classmethod
    def _sanitise(cls, v):
        return clean_text(v) if isinstance(v, str) else v


class ResearchRequestRead(BaseModel):
    # Deliberately does not echo back the submitted PII.
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    created_at: datetime
    # Echoed so the success screen can confirm the expedite quote (None for plain leads).
    price_eur: Optional[float] = None


# --- Court / deep-research order (logged-in, entity network page) -------------


class CourtResearchOrderCreate(BaseModel):
    """A logged-in member orders a court check on a company or its whole network.

    No CAPTCHA — login is the gate. The price is recomputed server-side from the
    live network (the client only shows an estimate), so nothing here carries money.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    key: str = Field(min_length=1, max_length=64)          # entity key (EIK or person_key)
    scope: Literal["company", "network"]
    search_type: Literal["eik", "eik_name"]
    depth: int = Field(default=2, ge=1, le=4)
    details: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("details", mode="before")
    @classmethod
    def _sanitise(cls, v):
        return clean_text(v) if isinstance(v, str) else v


class CourtResearchOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    price_eur: Optional[float] = None
    entity_count: Optional[int] = None
    created_at: datetime


# --- Admin (superuser-only read views) ---------------------------------------


class AdminResearchRequestRead(BaseModel):
    """Full request row for the admin inbox — includes the submitter's contact
    details (the admin is the data owner). Superuser-gated at the route."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    status: str
    order_type: str
    company_name: str
    company_eik: Optional[str] = None
    owner: Optional[str] = None
    details: Optional[str] = None
    requester_name: Optional[str] = None
    requester_email: str
    search_query: Optional[str] = None
    scope: Optional[str] = None
    search_type: Optional[str] = None
    network_depth: Optional[int] = None
    entity_count: Optional[int] = None
    price_eur: Optional[float] = None
    expedited: bool = False
    user_id: Optional[int] = None

    # --- Coverage flags (derived, not stored on the request) -----------------
    # ``in_db``: the requested ЕИК resolves to an entity we hold.
    # ``court_checked_at``: when we last ran a legalacts search for that ЕИК —
    # read from ``court_check``, which logs zero-result searches too, so a clean
    # company still reads as checked. None = never searched, NOT "nothing found".
    in_db: bool = False
    entity_id: Optional[int] = None
    edge_count: int = 0
    court_checked_at: Optional[datetime] = None
    court_acts: Optional[int] = None


class AdminUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: Optional[str] = None
    tier: str
    is_active: bool
    is_superuser: bool
    is_verified: bool
