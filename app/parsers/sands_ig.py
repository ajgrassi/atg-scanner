"""Sands Investment Group / SIGNNN broker broadcast parser.

Sands IG's blasts cover car washes (mostly absolute NNN) and IOS. Subject
typically tells us which: 'Car Wash NNN For Sale' vs 'IOS / Yard For Sale'.
Body has the property highlights as LABEL: value pairs and usually
includes an OM PDF attachment.
"""

from __future__ import annotations

from ..gmail_client import EmailMessage
from .generic_broker import GenericBrokerEmailParser


class SandsIgParser(GenericBrokerEmailParser):
    source_id = "sands_ig"

    def identify_channel(self, message: EmailMessage) -> str:
        subject = (message.subject or "").lower()
        if any(kw in subject for kw in ("ios", "outdoor storage", "yard")):
            return "ios"
        return "car_wash_nnn"
