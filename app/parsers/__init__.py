"""Per-source parsers.

Each module exposes `parse(message: EmailMessage) -> list[Listing]`.
The routine maps a sender to a parser via `app.config.SOURCES`.
"""

from __future__ import annotations

from .base import Parser, ParseResult

__all__ = ["Parser", "ParseResult"]
