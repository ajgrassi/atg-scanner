"""GenericBrokerEmailParser — shared base for the broker-blast parsers.

Most CRE broker blasts follow the same shape:
  Subject: <listing headline> — sometimes includes price + city
  Body:    <headline> at the top
           <street>, <city>, <state> <zip>
           Property highlights as `LABEL: value` pairs separated by 2+ spaces
           or newlines
           A long-form description paragraph
           Contact info / signature block

This base extracts what it can; channel-specific subclasses override
`identify_channel()` and `extra_fields()` to add behavior. PDF attachments
are handled by chaining to `pdf_om.PdfOMParser` when present.
"""

from __future__ import annotations

import re
from typing import Any

from ..gmail_client import EmailMessage
from ..listing import Listing
from ..utils import get_logger
from .base import Parser, ParseResult
from .pdf_om import _ADDRESS, _LEASE_EXPIRY, _LEASE_TERM, extract_from_text

log = get_logger(__name__)


# LABEL: value head. Accepts TitleCase ("Asking Price") and ALL-CAPS ("SALE PRICE").
# Anchored on a leading uppercase letter so we don't match arbitrary "word: value"
# noise (e.g. "Note: please call ..." inside a description paragraph).
_LABEL_HEAD = re.compile(r"^([A-Z][A-Za-z][A-Za-z\s/\-]{1,40}?):\s+(.+)$")


def _parse_kv_block(block: str) -> dict[str, str]:
    """Convert 'LABEL: value  LABEL2: value2' / line-separated labels into a dict.

    Walks newline-separated lines first so multi-line broker blasts work, then
    splits each line on 2+ space gaps for the inline-LABEL: value style.
    """
    out: dict[str, str] = {}
    for line in block.splitlines():
        for chunk in re.split(r"\s{2,}", line):
            chunk = chunk.strip().rstrip(".")
            m = _LABEL_HEAD.match(chunk)
            if not m:
                continue
            label = re.sub(r"\s+", "_", m.group(1).strip().lower())
            out[label] = m.group(2).strip()
    return out


def _money_loose(text: str | None) -> int | None:
    if not text:
        return None
    m = re.search(r"\$?\s*([\d,\.]+)\s*(M|MM|K)?", text, re.I)
    if not m:
        return None
    try:
        v = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    s = (m.group(2) or "").upper()
    if s in ("M", "MM"):
        return int(v * 1_000_000)
    if s == "K":
        return int(v * 1_000)
    return int(v)


def _int_loose(text: str | None) -> int | None:
    if not text:
        return None
    m = re.search(r"([\d,]+)", text)
    if not m:
        return None
    try:
        return int(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _pct_loose(text: str | None) -> float | None:
    if not text:
        return None
    m = re.search(r"([\d.]+)\s*%?", text)
    if not m:
        return None
    try:
        return round(float(m.group(1)) / 100.0, 5)
    except ValueError:
        return None


class GenericBrokerEmailParser(Parser):
    """Default parser. Subclasses override `source_id`, `_default_channel()`,
    and (optionally) `identify_channel()` for senders that route by subject."""

    source_id = "generic_broker"

    def _default_channel(self) -> str:
        """The channel this source maps to when there's no per-message routing."""
        return "msa_commercial"

    def identify_channel(self, message: EmailMessage) -> str:
        """Override for senders (Crexi, LoopNet) that route by subject content."""
        return self._default_channel()

    def parse(self, message: EmailMessage) -> ParseResult:
        listings: list[Listing] = []
        warnings: list[str] = []

        # 1) Try to extract a listing from the email body.
        body_listing, body_warnings = self._parse_body(message)
        if body_listing:
            listings.append(body_listing)
        warnings.extend(body_warnings)

        # 2) Walk PDF attachments.
        for att in (message.attachments or []):
            if att.mime_type != "application/pdf" or not att.local_path:
                continue
            from .pdf_om import PdfOMParser
            pdf_result = PdfOMParser().parse_pdf(
                att.local_path, email_id=message.id,
                channel=self.identify_channel(message),
            )
            for L in pdf_result.listings:
                L.source = self.source_id
                listings.append(L)
            warnings.extend(pdf_result.warnings)

        confidence = max((L.extraction_confidence for L in listings), default=0.0)
        return ParseResult(
            listings=listings, warnings=warnings, extraction_confidence=confidence,
        )

    # ------------------------------------------------------------- helpers
    def _parse_body(self, message: EmailMessage) -> tuple[Listing | None, list[str]]:
        text = (message.text_body or "").replace("\xa0", " ")
        warnings: list[str] = []

        # Find an address.
        addr_match = _ADDRESS.search(text)
        if not addr_match:
            warnings.append(f"{self.source_id}: no address found in body")
            return None, warnings

        street, city, state, zip_code = addr_match.groups()
        address = f"{street}, {city}, {state} {zip_code}"

        # KV block — start at "Property Highlights" if present, otherwise
        # take the body region after the address line.
        marker_idx = text.lower().find("property highlights")
        if marker_idx >= 0:
            highlights_start = marker_idx + len("property highlights")
        else:
            highlights_start = addr_match.end()

        # End the KV block before any obvious description start.
        end_markers = [
            "property location", "property description", "investment highlights",
            "broker contact", "for more information", "available spaces",
            "executive summary", "deal summary",
        ]
        end_idx = len(text)
        for marker in end_markers:
            i = text.lower().find(marker, highlights_start)
            if i > 0:
                end_idx = min(end_idx, i)
        block = text[highlights_start:end_idx]

        fields = _parse_kv_block(block)

        # Extract canonical fields.
        price = _money_loose(
            fields.get("sale_price")
            or fields.get("asking_price")
            or fields.get("offering_price")
            or fields.get("price")
        )
        if price is None:
            # Fall back to the first dollar-figure in the body.
            m = re.search(r"\$\s*([\d,\.]+)\s*(M|MM|K)?", text, re.I)
            if m:
                price = _money_loose(m.group(0))

        sf = _int_loose(
            fields.get("building_size")
            or fields.get("size")
            or fields.get("rentable_sf")
            or fields.get("rentable_building_area")
            or fields.get("gla")
        )
        if not (price and sf):
            warnings.append(f"{self.source_id}: missing price or sf in body")
            return None, warnings

        # Optional fields.
        cap_rate = _pct_loose(fields.get("cap_rate") or fields.get("going_in_cap_rate"))
        noi = _money_loose(fields.get("noi") or fields.get("net_operating_income"))
        year_built = _int_loose(fields.get("year_built") or fields.get("year_built_renovated"))
        lot_acres = None
        if (lot_text := fields.get("lot_size") or fields.get("land_size")):
            m = re.search(r"([\d.]+)", lot_text)
            if m:
                try:
                    lot_acres = float(m.group(1))
                except ValueError:
                    pass

        tenant = fields.get("tenant") or self._tenant_from_subject(message.subject)
        lease_type = self._lease_type_from_text(
            fields.get("lease_type") or fields.get("lease_structure") or "")
        lease_term = None
        if (term_text := fields.get("lease_term") or fields.get("term_remaining")):
            m = _LEASE_TERM.search(f"lease term: {term_text}")
            if m:
                try:
                    lease_term = float(m.group(1))
                except ValueError:
                    pass

        escalator = _pct_loose(
            fields.get("rent_escalator") or fields.get("escalation")
            or fields.get("annual_increase"))
        roof = (fields.get("roof_responsibility") or fields.get("roof") or "").lower().strip() or None

        listing = Listing(
            source=self.source_id,
            channel=self.identify_channel(message),
            title=message.subject or address,
            address=address,
            city=city.strip(),
            state=state.upper(),
            zip=zip_code,
            price=price,
            sf=sf,
            cap_rate=cap_rate,
            noi=noi,
            lot_acres=lot_acres,
            tenant=tenant,
            lease_type=lease_type,
            term_remaining_years=lease_term,
            escalator_pct=escalator,
            roof_structure=roof if roof in ("tenant", "landlord", "shared") else None,
            bonus_dep_eligible=True if sf and sf >= 2000 else None,
            email_id=message.id,
            extraction_confidence=self._confidence(fields, address),
            needs_review=False,
            raw_data={
                "year_built": year_built,
                "highlights_fields": fields,
                "broker_email_sender": message.sender,
                "broker_email_subject": message.subject,
            },
        )
        listing.needs_review = listing.extraction_confidence < 0.7
        return listing, warnings

    @staticmethod
    def _confidence(fields: dict[str, str], address: str | None) -> float:
        score = 0.0
        score += 0.4 if address else 0
        score += 0.3 if any(k in fields for k in ("sale_price", "offering_price",
                                                  "asking_price", "price")) else 0
        score += 0.2 if any(k in fields for k in ("building_size", "size", "gla")) else 0
        score += 0.1 if any(k in fields for k in ("cap_rate", "noi", "tenant")) else 0
        return round(score, 2)

    @staticmethod
    def _lease_type_from_text(s: str) -> str | None:
        if not s:
            return None
        t = s.lower()
        if "absolute" in t:
            return "absolute_nnn"
        if "ground" in t:
            return "ground_lease"
        if "triple" in t or "nnn" in t:
            return "nnn"
        if "double" in t or "nn" in t:
            return "nn"
        return None

    @staticmethod
    def _tenant_from_subject(subject: str) -> str | None:
        """Subject lines like 'NEW LISTING — Mister Car Wash, Bridgeville PA'.

        Pulls the candidate name from after the dash if any.
        """
        if not subject:
            return None
        for sep in ("—", "–", " - ", ":"):
            if sep in subject:
                tail = subject.split(sep, 1)[1].strip()
                first_part = tail.split(",", 1)[0].strip()
                if first_part and first_part[:1].isalpha():
                    return first_part
        return None
