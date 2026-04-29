"""LoopNet saved-search alert email parser.

Mirror of crexi.py — same routing strategy (subject saved-search name)
and the same body shape with a LoopNet listing URL at the bottom.
"""

from __future__ import annotations

import re

from ..config import SAVED_SEARCH_TO_CHANNEL
from ..gmail_client import EmailMessage
from .generic_broker import GenericBrokerEmailParser


_LISTING_URL = re.compile(r"https?://(?:www\.)?loopnet\.com/Listing/[^\s)\]]+", re.I)
_LISTING_ID = re.compile(r"/Listing/[^/]+/(\d+)/?")


class LoopnetParser(GenericBrokerEmailParser):
    source_id = "loopnet"

    def identify_channel(self, message: EmailMessage) -> str:
        subject = (message.subject or "").lower()
        for keyword, channel in SAVED_SEARCH_TO_CHANNEL.items():
            if keyword in subject:
                return channel
        return "msa_commercial"

    def parse(self, message: EmailMessage):
        result = super().parse(message)
        m = _LISTING_URL.search(message.text_body or "")
        if m:
            for L in result.listings:
                if not L.listing_url:
                    L.listing_url = m.group(0)
                m2 = _LISTING_ID.search(m.group(0))
                if m2 and not L.source_listing_id:
                    L.source_listing_id = m2.group(1)
        return result
