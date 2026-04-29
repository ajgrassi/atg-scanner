"""Crexi saved-search alert email parser.

Crexi sends one email per saved search per match. Channel routes by the
subject's saved-search name (config.SAVED_SEARCH_TO_CHANNEL). Body shape:

  Subject: New Match for Your Saved Search: <Saved Search Name>
  Body:    <Property Title>
           <street>, <city>, <state> <zip>
           Property Type: <type>
           Asking Price: $<price>
           Building Size: <sf> SF
           Cap Rate: <pct>%
           View Listing on Crexi → <url>
"""

from __future__ import annotations

import re

from ..config import SAVED_SEARCH_TO_CHANNEL
from ..gmail_client import EmailMessage
from .generic_broker import GenericBrokerEmailParser


_LISTING_URL = re.compile(r"https?://(?:www\.)?crexi\.com/properties/[^\s)\]]+", re.I)


class CrexiParser(GenericBrokerEmailParser):
    source_id = "crexi"

    def identify_channel(self, message: EmailMessage) -> str:
        subject = (message.subject or "").lower()
        for keyword, channel in SAVED_SEARCH_TO_CHANNEL.items():
            if keyword in subject:
                return channel
        return "msa_commercial"     # safe default — proforma will gate

    def parse(self, message: EmailMessage):
        result = super().parse(message)
        # Capture the listing URL when present in the body.
        m = _LISTING_URL.search(message.text_body or "")
        if m:
            for L in result.listings:
                if not L.listing_url:
                    L.listing_url = m.group(0)
                # Crexi's URL embeds the listing id as the slug-prefix segment.
                slug = m.group(0).rstrip("/").rsplit("/", 1)[-1]
                if slug and not L.source_listing_id:
                    L.source_listing_id = slug
        return result
