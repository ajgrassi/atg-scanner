"""Solar farm scorer — Phase 2 stub."""

from __future__ import annotations

from ..listing import Listing, ScoreResult
from .base import Scorer


class SolarScorer(Scorer):
    channel = "solar"

    def structural_gates(self, listing: Listing) -> tuple[bool, list[str]]:
        failed: list[str] = []
        raw = listing.raw_data or {}
        if raw.get("is_development_only"):
            failed.append("development_only_not_operational")
        ppa = raw.get("ppa_term_remaining_years")
        if ppa is not None and ppa < 15:
            failed.append(f"ppa_term_remaining_{ppa}y_below_15y")
        if raw.get("is_residential_rooftop"):
            failed.append("residential_rooftop_excluded")
        if raw.get("is_community_solar"):
            failed.append("community_solar_excluded")
        return (not failed), failed

    def score(self, listing: Listing) -> ScoreResult:
        return ScoreResult(
            score=0.0, verdict="WATCH",
            components={"_phase2_pending": 0.0},
            notes=["solar scoring not yet implemented (Phase 2)"],
        )
