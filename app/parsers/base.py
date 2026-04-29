"""Parser ABC. Each broker email source ships a Parser implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..gmail_client import EmailMessage
from ..listing import Listing


@dataclass
class ParseResult:
    """Output of Parser.parse(). Listings + per-message diagnostics."""

    listings: list[Listing] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    extraction_confidence: float = 1.0


class Parser(ABC):
    """Each parser corresponds to ONE source domain (or one alert sender).

    Phase-1 stubs return an empty ParseResult so the routine doesn't crash
    when it encounters those senders. Phase-3+ fills in real parsing.
    """

    source_id: str = ""           # short id, e.g. "crexi"

    @abstractmethod
    def parse(self, message: EmailMessage) -> ParseResult:
        """Extract listings from a single Gmail message."""

    def _stub_result(self, message: EmailMessage, note: str) -> ParseResult:
        return ParseResult(
            listings=[],
            warnings=[f"{self.source_id}: {note} (msg={message.id})"],
            extraction_confidence=0.0,
        )
