"""Matthews Real Estate broker broadcast.

Matthews covers car wash NNN AND msa-area commercial. Subject keywords route.
"""

from __future__ import annotations

from ..gmail_client import EmailMessage
from .generic_broker import GenericBrokerEmailParser


class MatthewsParser(GenericBrokerEmailParser):
    source_id = "matthews"

    def identify_channel(self, message: EmailMessage) -> str:
        subject = (message.subject or "").lower()
        if any(kw in subject for kw in ("car wash", "carwash", "express tunnel")):
            return "car_wash_nnn"
        if any(kw in subject for kw in ("retail", "office", "commercial",
                                         "springfield", "ozark", "nixa", "branson")):
            return "msa_commercial"
        return "car_wash_nnn"

    def _default_channel(self) -> str:
        return "car_wash_nnn"
