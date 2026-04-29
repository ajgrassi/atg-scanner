"""Industrial Outdoor Storage scorer — Phase 2 stub."""

from __future__ import annotations

from ..listing import Listing, ScoreResult
from .base import Scorer


class IOSScorer(Scorer):
    channel = "ios"

    def structural_gates(self, listing: Listing) -> tuple[bool, list[str]]:
        failed: list[str] = []
        raw = listing.raw_data or {}
        if not (2_000_000 <= listing.price <= 5_000_000):
            failed.append("price_outside_band_2M_to_5M")
        usable = listing.lot_acres or raw.get("usable_acres")
        if usable is not None and usable < 2.0:
            failed.append(f"usable_acres_{usable}_below_2.0")
        if raw.get("is_vacant_land_speculation"):
            failed.append("vacant_land_speculation_excluded")
        return (not failed), failed

    def score(self, listing: Listing) -> ScoreResult:
        return ScoreResult(
            score=0.0, verdict="WATCH",
            components={"_phase2_pending": 0.0},
            notes=["ios scoring not yet implemented (Phase 2)"],
        )
