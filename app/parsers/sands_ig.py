"""Sands Investment Group / SIGNNN broker broadcast parser.

Sands IG blasts cover car washes, IOS, and general NNN. Subject typically
tells us which: 'Car Wash NNN For Sale' vs 'IOS / Yard For Sale'.

Email format (typical Sands IG broadcast):
  Intro paragraph: "… offer for sale the X SF <TENANT> NNN Asset located at
                    <STREET> in <CITY>, <STATE>."
  Then a header line: "<PROPERTY NAME> - <CITY>, <STATE>"
  Then PRICE / CAP RATE / SQUARE FOOTAGE as two-line label/value blocks.
  Then an "Investment Highlights" section (freeform).
  Then "Investment Advisors" contact block.
"""

from __future__ import annotations

import re
from typing import Any

from ..gmail_client import EmailMessage
from ..listing import Listing
from ..utils import get_logger
from .base import ParseResult
from .generic_broker import (
    GenericBrokerEmailParser,
    _money_loose,
    _int_loose,
    _pct_loose,
)

log = get_logger(__name__)


# "at 275 Enterprise Drive in Valdosta, GA"
# "at 7384-7392 Industry Drive in North Charleston, SC"
# "at 2852 Holcomb Bridge Road in Alpharetta, GA"
_SIG_ADDR = re.compile(
    r"\bat\s+"
    r"(\d[\w\s\-\.\,']{3,80}?)"   # street (starting with digit)
    r"\s+in\s+"
    r"([A-Za-z][A-Za-z\s\-\.]{1,40}?)"  # city
    r",\s*"
    r"([A-Z]{2}|[A-Za-z]+)",             # state abbrev or full name
    re.I,
)

# Two-line label/value blocks used by Sands IG:
#   PRICE
#   $2,285,714
_SIG_PRICE = re.compile(r"PRICE\s+\$\s*([\d,]+)", re.I)
_SIG_CAP = re.compile(r"CAP\s*RATE\s+([\d.]+)\s*%", re.I)
_SIG_SF = re.compile(r"SQUARE\s*FOOTAGE\s+([\d,]+)\s*SF", re.I)
_SIG_LEASE_TERM = re.compile(r"([\d.]+)\+?\s*(?:years?|yr)", re.I)
_SIG_ESCALATOR = re.compile(r"([\d.]+)\s*%\s*annual", re.I)

# US state abbreviation → full name map (subset; enough for Sands coverage)
_STATE_NORM: dict[str, str] = {
    "georgia": "GA", "ohio": "OH", "west virginia": "WV",
    "south carolina": "SC", "north carolina": "NC",
    "florida": "FL", "tennessee": "TN", "texas": "TX",
    "california": "CA", "louisiana": "LA", "illinois": "IL",
    "massachusetts": "MA", "new york": "NY", "virginia": "VA",
    "pennsylvania": "PA", "oklahoma": "OK", "kansas": "KS",
    "missouri": "MO", "colorado": "CO", "arizona": "AZ",
}


def _norm_state(raw: str) -> str:
    s = raw.strip()
    if len(s) == 2:
        return s.upper()
    return _STATE_NORM.get(s.lower(), s.upper()[:2])


class SandsIgParser(GenericBrokerEmailParser):
    source_id = "sands_ig"

    def identify_channel(self, message: EmailMessage) -> str:
        subject = (message.subject or "").lower()
        if any(kw in subject for kw in ("ios", "outdoor storage", "yard")):
            return "ios"
        return "car_wash_nnn"

    def _parse_body(self, message: EmailMessage) -> tuple[Listing | None, list[str]]:
        text = (message.text_body or "").replace("\xa0", " ").replace("‌", "")
        warnings: list[str] = []

        # Skip "For Lease" blasts — we want for-sale only.
        if re.search(r"\bfor\s+lease\b", text, re.I) and not re.search(r"\bfor\s+sale\b", text, re.I):
            warnings.append(f"{self.source_id}: skipping for-lease-only listing")
            return None, warnings

        # ── Address ──────────────────────────────────────────────────────
        addr_m = _SIG_ADDR.search(text)
        if not addr_m:
            # Fall back to generic parser which handles traditional format.
            return super()._parse_body(message)

        street = addr_m.group(1).strip().rstrip(",")
        city = addr_m.group(2).strip()
        state = _norm_state(addr_m.group(3))
        address = f"{street}, {city}, {state}"

        # ── Financials ────────────────────────────────────────────────────
        price_m = _SIG_PRICE.search(text)
        sf_m = _SIG_SF.search(text)

        # Price fallback: first dollar figure in body.
        if not price_m:
            dm = re.search(r"\$\s*([\d,]+)", text)
            price = _money_loose(dm.group(0)) if dm else None
        else:
            price = _money_loose("$" + price_m.group(1))

        sf = _int_loose(sf_m.group(1)) if sf_m else None

        # No price → skip (retail development "call for pricing" type).
        if not price:
            warnings.append(f"{self.source_id}: no price found — skipping {address}")
            return None, warnings

        # No SF from SQUARE FOOTAGE block → try inline pattern.
        if not sf:
            sf_inline = re.search(r"([\d,]+)\s*SF\b", text, re.I)
            sf = _int_loose(sf_inline.group(1)) if sf_inline else None

        cap_m = _SIG_CAP.search(text)
        cap_rate = float(cap_m.group(1)) / 100.0 if cap_m else None

        # ── Lease details ─────────────────────────────────────────────────
        lease_type = self._lease_type_from_text(
            "absolute nnn" if re.search(r"absolute\s*nnn", text, re.I)
            else "ground lease" if re.search(r"ground\s+lease", text, re.I)
            else "nnn" if re.search(r"\bnnn\b|\btriple\s*net\b", text, re.I)
            else ""
        )

        # Term remaining from "X+ years remaining" pattern.
        term_remaining = None
        term_m = re.search(r"([\d.]+)\+?\s*years?\s+remaining", text, re.I)
        if term_m:
            try:
                term_remaining = float(term_m.group(1))
            except ValueError:
                pass
        if term_remaining is None:
            # "XX+ Year NNN" in subject line.
            subj_term = re.search(r"(\d+)\+?\s*-?\s*Year", message.subject or "", re.I)
            if subj_term:
                try:
                    term_remaining = float(subj_term.group(1))
                except ValueError:
                    pass

        escalator = None
        esc_m = _SIG_ESCALATOR.search(text)
        if esc_m:
            try:
                escalator = float(esc_m.group(1)) / 100.0
            except ValueError:
                pass
        if escalator is None:
            esc_subj = re.search(r"(\d+(?:\.\d+)?)\s*%\s*annual", message.subject or "", re.I)
            if esc_subj:
                try:
                    escalator = float(esc_subj.group(1)) / 100.0
                except ValueError:
                    pass

        # ── Tenant ────────────────────────────────────────────────────────
        # Grab from intro paragraph "offer for sale the X SF <TENANT>"
        tenant = None
        intro_m = re.search(
            r"offer(?:ing)?\s+for\s+sale\s+the\s+[\d,]+\s*SF\s+([A-Z][A-Za-z &]+?)(?:\s+NNN|\s+Ground|\s+Asset|\s+facility|\s+of\s)",
            text, re.I,
        )
        if intro_m:
            tenant = intro_m.group(1).strip()
        else:
            tenant = self._tenant_from_subject(message.subject)

        # Tenant credit classification.
        tenant_credit = self._classify_tenant_credit(tenant or "")

        # Roof/bonus dep for car wash → not extractable from these emails;
        # leave as None (scorer's structural gates will fire).
        listing = Listing(
            source=self.source_id,
            channel=self.identify_channel(message),
            title=message.subject or address,
            address=address,
            city=city,
            state=state,
            zip=None,
            price=price,
            sf=sf,
            cap_rate=cap_rate,
            noi=None,
            lot_acres=None,
            tenant=tenant,
            tenant_credit=tenant_credit,
            lease_type=lease_type,
            term_remaining_years=term_remaining,
            escalator_pct=escalator,
            roof_structure=None,
            bonus_dep_eligible=None,
            email_id=message.id,
            extraction_confidence=self._sig_confidence(price, sf, cap_rate, address),
            needs_review=False,
            raw_data={
                "broker_email_sender": message.sender,
                "broker_email_subject": message.subject,
            },
        )
        listing.needs_review = listing.extraction_confidence < 0.7
        return listing, warnings

    # ── helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _sig_confidence(price, sf, cap_rate, address) -> float:
        score = 0.0
        score += 0.4 if address else 0.0
        score += 0.3 if price else 0.0
        score += 0.2 if sf else 0.0
        score += 0.1 if cap_rate else 0.0
        return round(score, 2)

    @staticmethod
    def _classify_tenant_credit(tenant: str) -> str | None:
        if not tenant:
            return None
        t = tenant.lower()
        # Publicly traded / investment-grade corporate guarantees.
        public_keywords = [
            "nasdaq", "nyse", "ahold", "delhaize", "white castle", "stop & shop",
            "acadia healthcare", "dollar general", "dollar tree", "walgreens",
            "cvs", "7-eleven", "mcdonald", "starbucks", "autozone",
            "o'reilly", "advance auto", "tractor supply",
        ]
        if any(kw in t for kw in public_keywords):
            return "public_corporate"
        # Large private chains (100+ units).
        large_private = [
            "childcare network", "parker-chase", "parker chase", "endeavor school",
            "chugach", "kinder", "learning care",
        ]
        if any(kw in t for kw in large_private):
            return "private_large"
        return "private_small"
