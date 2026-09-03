"""Wire format for a findings bundle pushed from the research machine.

Entities are addressed by **natural key** — ЕИК for companies, ``person_key``
for persons — never by database id, because local ids and production ids are
unrelated. Edges name their endpoints the same way and the server resolves them.

Structural rules that would corrupt production are enforced here, before any
database work: a company without an ЕИК cannot be deduplicated, and a person
without a ``person_key`` would either duplicate on every re-push or (with a
fuzzy name fallback) merge two different people.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EntityRef(BaseModel):
    """Points at an entity by natural key. Exactly one of the two is required."""

    model_config = ConfigDict(extra="forbid")

    eik: Optional[str] = None
    person_key: Optional[str] = None

    @model_validator(mode="after")
    def _exactly_one_key(self) -> "EntityRef":
        if bool(self.eik) == bool(self.person_key):
            raise ValueError("entity reference needs exactly one of eik / person_key")
        return self


class EntityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["company", "person"]
    name: str
    eik: Optional[str] = None
    person_key: Optional[str] = None
    legal_form: Optional[str] = None
    status: Optional[str] = None
    address: Optional[str] = None
    capital_eur: Optional[float] = None   # converted to capital_bgn at the peg
    founded_year: Optional[int] = None
    source: Optional[str] = None

    # запор върху дружествен дял. Explicitly settable to False so a lifted
    # attachment can be cleared — the enrich-don't-erase rule skips None, not False.
    has_seizure: Optional[bool] = None
    seizure_count: Optional[int] = None
    seizure_last_at: Optional[date] = None
    seizure_source_url: Optional[str] = None

    @model_validator(mode="after")
    def _key_matches_kind(self) -> "EntityIn":
        if self.kind == "company" and not self.eik:
            raise ValueError("company entity requires eik")
        if self.kind == "person" and not self.person_key:
            raise ValueError("person entity requires person_key")
        return self


class BuilderIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eik: str
    name: str
    legal_form: Optional[str] = None
    address: Optional[str] = None
    capital_bgn: Optional[float] = None
    status: Optional[str] = None
    ksb_category: Optional[str] = None
    ksb_active: Optional[bool] = None
    insolvency_flag: Optional[bool] = None
    tax_debt_bgn: Optional[float] = None


class EdgeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    src: EntityRef
    dst: EntityRef
    relation: Literal["ownership", "management"]
    share_pct: Optional[float] = None
    role: Optional[str] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    is_current: bool = True
    source: Optional[str] = None


class SignalIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_kind: Literal["company", "person"]
    matched_name: str
    url: str
    source_type: str          # registry | forum | web
    tier: str                 # official | community | web
    match_confidence: str     # eik | fuzzy_high | fuzzy_low
    matched_eik: Optional[str] = None
    matched_person_key: Optional[str] = None
    title: Optional[str] = None
    snippet: Optional[str] = None
    source_site: Optional[str] = None
    observed_date: Optional[date] = None
    scraped_at: Optional[datetime] = None


class CourtCheckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eik: str
    checked_at: datetime
    name: Optional[str] = None
    method: str = "eik"
    acts_found: int = 0
    source_site: str = "legalacts.justice.bg"


class Bundle(BaseModel):
    """Everything one research session produced, applied in one transaction."""

    model_config = ConfigDict(extra="forbid")

    entities: List[EntityIn] = Field(default_factory=list)
    builder: Optional[BuilderIn] = None
    edges: List[EdgeIn] = Field(default_factory=list)
    signals: List[SignalIn] = Field(default_factory=list)
    court_checks: List[CourtCheckIn] = Field(default_factory=list)
    report_md: Optional[str] = None
    notes: Optional[str] = None
