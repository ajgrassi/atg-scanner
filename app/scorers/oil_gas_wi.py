"""Oil & Gas Working Interests — Phase 2 stub."""

from __future__ import annotations

from ..listing import Listing, ScoreResult
from .base import Scorer


class OilGasWIScorer(Scorer):
    channel = "oil_gas_wi"

    def structural_gates(self, listing: Listing) -> tuple[bool, list[str]]:
        failed: list[str] = []
        raw = listing.raw_data or {}
        if raw.get("is_fund"):
            failed.append("excluded_fund_structure")
        if raw.get("is_royalty_only"):
            failed.append("excluded_royalty_only")
        if not (250_000 <= listing.price <= 1_500_000):
            failed.append("investment_outside_band_250k_to_1.5M")
        return (not failed), failed

    def score(self, listing: Listing) -> ScoreResult:
        return ScoreResult(
            score=0.0, verdict="WATCH",
            components={"_phase2_pending": 0.0},
            notes=["oil_gas_wi scoring not yet implemented (Phase 2)"],
        )
