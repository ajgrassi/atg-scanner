"""Scorer ABC. Every channel scorer subclasses this."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..listing import Listing, ScoreResult


class Scorer(ABC):
    """Each Scorer corresponds to ONE channel.

    Two methods:
      - structural_gates() rejects a listing outright on hard requirements.
      - score() produces a 0–100 score with components + verdict.

    Convention: a structural fail short-circuits scoring. The routine should
    call structural_gates() first; if it returns (False, reasons), tag the
    listing STRUCTURAL_FAIL and skip scoring.
    """

    channel: str = ""

    @abstractmethod
    def structural_gates(self, listing: Listing) -> tuple[bool, list[str]]:
        """Return (all_passed, list_of_failed_gate_names)."""

    @abstractmethod
    def score(self, listing: Listing) -> ScoreResult:
        """Return ScoreResult with score 0–100 and component breakdown."""

    def evaluate(self, listing: Listing) -> ScoreResult:
        """Convenience: gates → score, returns STRUCTURAL_FAIL on gate failure."""
        ok, failed = self.structural_gates(listing)
        if not ok:
            return ScoreResult(
                score=0.0,
                verdict="STRUCTURAL_FAIL",
                structural_failures=failed,
                notes=[f"Failed gates: {', '.join(failed)}"],
            )
        return self.score(listing)
