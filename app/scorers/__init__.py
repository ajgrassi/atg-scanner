"""Scorers — one per channel.

Discovery: SCORER_BY_CHANNEL maps channel name → Scorer factory. The
routine resolves a Listing's channel and dispatches to the matching scorer.
"""

from __future__ import annotations

from .base import Scorer, ScoreResult
from .carwash_nnn import CarwashNNNScorer
from .ios import IOSScorer
from .msa_commercial import MsaCommercialScorer
from .oil_gas_wi import OilGasWIScorer
from .self_storage import SelfStorageScorer
from .solar import SolarScorer

SCORER_BY_CHANNEL: dict[str, type[Scorer]] = {
    "car_wash_nnn":   CarwashNNNScorer,
    "msa_commercial": MsaCommercialScorer,
    "self_storage":   SelfStorageScorer,
    "oil_gas_wi":     OilGasWIScorer,
    "solar":          SolarScorer,
    "ios":            IOSScorer,
}


def get_scorer(channel: str) -> Scorer:
    cls = SCORER_BY_CHANNEL.get(channel)
    if cls is None:
        raise KeyError(f"No scorer registered for channel '{channel}'")
    return cls()


__all__ = ["Scorer", "ScoreResult", "SCORER_BY_CHANNEL", "get_scorer"]
