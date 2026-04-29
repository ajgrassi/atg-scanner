"""Self-storage scorer (incl. RV/boat) — Phase 2 stub."""

from __future__ import annotations

from ..listing import Listing, ScoreResult
from .base import Scorer

EXCLUDED_STATES = {"CA", "NY"}


class SelfStorageScorer(Scorer):
    channel = "self_storage"

    def structural_gates(self, listing: Listing) -> tuple[bool, list[str]]:
        failed: list[str] = []
        if (listing.state or "").upper() in EXCLUDED_STATES:
            failed.append(f"excluded_state_{listing.state}")
        if not (1_500_000 <= listing.price <= 5_000_000):
            failed.append("price_outside_band_1.5M_to_5M")
        # Occupancy ≥70% OR clear value-add story — value-add is parser-derived.
        occ = (listing.raw_data or {}).get("occupancy_pct")
        value_add = bool((listing.raw_data or {}).get("value_add_story"))
        if occ is not None and occ < 70 and not value_add:
            failed.append("occupancy_below_70_no_value_add_story")
        return (not failed), failed

    def score(self, listing: Listing) -> ScoreResult:
        return ScoreResult(
            score=0.0, verdict="WATCH",
            components={"_phase2_pending": 0.0},
            notes=["self_storage scoring not yet implemented (Phase 2)"],
        )
