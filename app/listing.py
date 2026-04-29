"""The Listing dataclass — single source of truth for the normalized shape.

Parsers emit Listings. Scorers consume Listings. The DB persists Listings.
Mirrors LISTING SCHEMA in CLAUDE.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

Verdict = Literal[
    "PURSUE",
    "PURSUE_CONDITIONS",
    "WATCH",
    "PASS",
    "STRUCTURAL_FAIL",
    "NEEDS_REVIEW",
]

TenantCredit = Literal[
    "public_corporate",
    "private_large",
    "private_small",
    "franchisee",
]

LeaseType = Literal[
    "absolute_nnn",
    "nnn",
    "nn",
    "ground_lease",
]

RoofStructure = Literal[
    "tenant",
    "landlord",
    "shared",
]


@dataclass
class Listing:
    # Identity
    source: str
    channel: str
    title: str
    address: str
    city: str
    state: str
    price: int
    email_id: str

    # Optional identity
    source_listing_id: str | None = None
    listing_url: str | None = None
    zip: str | None = None

    # Financials
    cap_rate: float | None = None
    noi: int | None = None
    sf: int | None = None
    lot_acres: float | None = None

    # Lease
    tenant: str | None = None
    tenant_credit: TenantCredit | None = None
    lease_type: LeaseType | None = None
    lease_start: date | None = None
    lease_expiration: date | None = None
    term_remaining_years: float | None = None
    escalator_pct: float | None = None
    roof_structure: RoofStructure | None = None

    # Tax
    bonus_dep_eligible: bool | None = None
    estimated_cost_seg_pct: float | None = None

    # Metadata
    extraction_confidence: float = 1.0
    needs_review: bool = False
    raw_data: dict[str, Any] = field(default_factory=dict)
    first_seen: datetime | None = None
    last_seen: datetime | None = None


@dataclass
class ScoreResult:
    """Output of a Scorer.score(listing)."""

    score: float                                 # 0–100
    verdict: Verdict
    components: dict[str, float] = field(default_factory=dict)
    structural_failures: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
