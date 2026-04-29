"""Generic PDF Offering Memorandum parser using pdfplumber.

Extracts the canonical Listing fields from any CRE OM (car wash, retail,
self-storage, IOS — same regex strategy works for all). Each scorer's
structural gates apply afterwards based on the channel.

Architecture (decoupled for testability):
  - extract_from_text(text)  → (Listing | None, ParseResult)  # pure regex; no I/O
  - parse_pdf(path)          → ParseResult                    # opens PDF + delegates
  - parse(message)           → ParseResult                    # walks email attachments
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ..gmail_client import EmailMessage
from ..listing import Listing
from ..utils import get_logger
from .base import Parser, ParseResult

log = get_logger(__name__)


# ----------------------------------------------------------------- regexes

_PRICE_LABEL = re.compile(
    r"(?:offering\s+price|asking\s+price|sale\s+price|list\s+price|price)"
    r"\s*[:\-]?\s*\$?([\d,\.]+)\s*(M|MM|K)?",
    re.I,
)
_PRICE_INLINE = re.compile(r"\$\s*([\d,\.]+)\s*(M|MM|K)?\s*(?:million|thousand)?", re.I)

_SF_LABEL = re.compile(
    r"(?:building\s+size|gross\s+leasable|rentable|gross\s+building|sq(?:uare)?\.?\s*ft|GLA)"
    r"[\s:\-]*([\d,]+)\s*(?:sf|sq\.?\s*ft)?",
    re.I,
)
_LOT_LABEL = re.compile(
    r"(?:lot\s+size|land\s+size|site\s+size|land\s+area|acreage)"
    r"\s*[:\-]?\s*([\d.]+)\s*(?:ac|acres)",
    re.I,
)
_CAP_LABEL = re.compile(
    r"(?:cap\s+rate|capitalization\s+rate)\s*[:\-]?\s*([\d.]+)\s*%",
    re.I,
)
_NOI_LABEL = re.compile(
    r"(?:NOI|net\s+operating\s+income)\s*[:\-]?\s*\$?([\d,\.]+)\s*(M|MM|K)?",
    re.I,
)
_YEAR_BUILT = re.compile(r"(?:year\s+built|yr\s+built|built|constructed)\s*[:\-]?\s*(\d{4})", re.I)
_TENANT_LABEL = re.compile(r"(?:tenant|operator)\s*[:\-]\s*([A-Z][^\n]{1,80})", re.I)
_LEASE_TYPE = re.compile(
    r"(?:lease\s+type|lease\s+structure)\s*[:\-]\s*"
    r"(absolute\s+(?:NNN|net|triple\s+net)|triple\s+net|NNN|double\s+net|NN|"
    r"ground\s+lease|gross\s+lease|modified\s+gross)",
    re.I,
)
_LEASE_TERM = re.compile(
    r"(?:lease\s+term|term\s+remaining|remaining\s+term|years\s+remaining)"
    r"\s*[:\-]?\s*([\d.]+)\s*(?:years|yrs|year)",
    re.I,
)
_LEASE_EXPIRY = re.compile(
    r"(?:lease\s+expir(?:ation|y)|expires?|maturity)\s*[:\-]?\s*"
    r"(\d{1,2}/\d{1,2}/\d{2,4}|[A-Z][a-z]+\s+\d{1,2},?\s+\d{4}|\d{4})",
    re.I,
)
_ESCALATOR = re.compile(
    r"(?:rent\s+(?:escalator|increase|bump)|escalat(?:ion|or)|annual\s+increase)"
    r"[\s:\-]*([\d.]+)\s*%",
    re.I,
)
_ROOF_RESP = re.compile(
    r"(?:roof|landlord\s+responsibilit|tenant\s+responsibilit)[^\.]{0,80}"
    r"(tenant|landlord|shared)",
    re.I,
)
_ADDRESS = re.compile(
    r"\b(\d{1,6}\s+[A-Z0-9][A-Za-z0-9\.\s\-']{1,80}?),\s+"
    r"([A-Z][A-Za-z\.\s\-']{1,40}?),\s+"
    r"([A-Z]{2})\s+(\d{5})(?:-\d{4})?",
    re.MULTILINE,
)


def _money(value: str, suffix: str | None) -> int | None:
    try:
        v = float(value.replace(",", ""))
    except ValueError:
        return None
    s = (suffix or "").upper()
    if s in ("M", "MM"):
        return int(v * 1_000_000)
    if s == "K":
        return int(v * 1_000)
    return int(v)


def _maybe_int(text: str | None) -> int | None:
    if text is None:
        return None
    try:
        return int(text.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def _confidence(extracted: dict[str, Any]) -> float:
    """Confidence is share of the must-have fields successfully extracted.

    Must-haves: address, price, sf. Nice-to-haves bump the score modestly.
    """
    must = ("address", "price", "sf")
    nice = ("cap_rate", "noi", "year_built", "tenant", "lease_type",
            "term_remaining_years", "escalator_pct", "roof_structure")
    must_hit = sum(1 for k in must if extracted.get(k) is not None) / len(must)
    nice_hit = sum(1 for k in nice if extracted.get(k) is not None) / len(nice)
    return round(0.7 * must_hit + 0.3 * nice_hit, 2)


def extract_from_text(text: str, *, source: str = "pdf_om",
                      email_id: str = "", channel: str = "") -> tuple[Listing | None, ParseResult]:
    """Pull a Listing out of pre-extracted PDF text.

    Returns (Listing | None, ParseResult). The ParseResult always has the
    extracted-confidence + warnings; the Listing is None when must-haves
    are missing.
    """
    extracted: dict[str, Any] = {}
    warnings: list[str] = []

    # Address
    m = _ADDRESS.search(text)
    if m:
        street, city, state, zip_code = m.group(1), m.group(2), m.group(3), m.group(4)
        extracted["address"] = f"{street}, {city}, {state} {zip_code}"
        extracted["city"] = city
        extracted["state"] = state.upper()
        extracted["zip"] = zip_code
    else:
        warnings.append("address pattern not found")

    # Price
    m = _PRICE_LABEL.search(text)
    if m:
        extracted["price"] = _money(m.group(1), m.group(2))
    else:
        m2 = _PRICE_INLINE.search(text)
        if m2:
            extracted["price"] = _money(m2.group(1), m2.group(2))
        else:
            warnings.append("price not found")

    # SF
    m = _SF_LABEL.search(text)
    if m:
        extracted["sf"] = _maybe_int(m.group(1))
    else:
        warnings.append("sf not found")

    # Lot size
    m = _LOT_LABEL.search(text)
    if m:
        try:
            extracted["lot_acres"] = float(m.group(1))
        except ValueError:
            pass

    # Cap rate
    m = _CAP_LABEL.search(text)
    if m:
        try:
            extracted["cap_rate"] = round(float(m.group(1)) / 100.0, 5)
        except ValueError:
            pass

    # NOI
    m = _NOI_LABEL.search(text)
    if m:
        extracted["noi"] = _money(m.group(1), m.group(2))

    # Year built
    m = _YEAR_BUILT.search(text)
    if m:
        try:
            extracted["year_built"] = int(m.group(1))
        except ValueError:
            pass

    # Tenant
    m = _TENANT_LABEL.search(text)
    if m:
        extracted["tenant"] = m.group(1).strip().rstrip(".,")

    # Lease type
    m = _LEASE_TYPE.search(text)
    if m:
        raw = m.group(1).lower()
        if "absolute" in raw:
            extracted["lease_type"] = "absolute_nnn"
        elif "ground" in raw:
            extracted["lease_type"] = "ground_lease"
        elif "triple" in raw or raw == "nnn":
            extracted["lease_type"] = "nnn"
        elif "double" in raw or raw == "nn":
            extracted["lease_type"] = "nn"

    # Lease term remaining
    m = _LEASE_TERM.search(text)
    if m:
        try:
            extracted["term_remaining_years"] = float(m.group(1))
        except ValueError:
            pass

    # Lease expiry
    m = _LEASE_EXPIRY.search(text)
    if m:
        extracted["lease_expiration"] = _parse_date(m.group(1))

    # Escalator %
    m = _ESCALATOR.search(text)
    if m:
        try:
            extracted["escalator_pct"] = round(float(m.group(1)) / 100.0, 5)
        except ValueError:
            pass

    # Roof responsibility
    m = _ROOF_RESP.search(text)
    if m:
        extracted["roof_structure"] = m.group(1).lower()

    # Bonus dep eligibility — heuristic: any commercial sale with a building
    # >= 2000 SF is bonus-dep eligible under current rules. Calibrate later.
    if extracted.get("sf") and extracted["sf"] >= 2000:
        extracted["bonus_dep_eligible"] = True

    confidence = _confidence(extracted)

    if not (extracted.get("address") and extracted.get("price") and extracted.get("sf")):
        return None, ParseResult(
            listings=[], warnings=warnings + ["missing one of address/price/sf"],
            extraction_confidence=confidence,
        )

    listing = Listing(
        source=source,
        channel=channel or "msa_commercial",
        title=extracted.get("tenant") or extracted["address"],
        address=extracted["address"],
        city=extracted.get("city") or "",
        state=extracted.get("state") or "",
        zip=extracted.get("zip"),
        price=int(extracted["price"]),
        sf=extracted["sf"],
        cap_rate=extracted.get("cap_rate"),
        noi=extracted.get("noi"),
        lot_acres=extracted.get("lot_acres"),
        tenant=extracted.get("tenant"),
        lease_type=extracted.get("lease_type"),
        lease_expiration=extracted.get("lease_expiration"),
        term_remaining_years=extracted.get("term_remaining_years"),
        escalator_pct=extracted.get("escalator_pct"),
        roof_structure=extracted.get("roof_structure"),
        bonus_dep_eligible=extracted.get("bonus_dep_eligible"),
        email_id=email_id,
        extraction_confidence=confidence,
        needs_review=confidence < 0.7,
        raw_data={"year_built": extracted.get("year_built")},
    )
    return listing, ParseResult(
        listings=[listing], warnings=warnings, extraction_confidence=confidence,
    )


def _parse_date(s: str) -> date | None:
    s = s.strip()
    formats = (
        "%m/%d/%Y", "%m/%d/%y",
        "%B %d, %Y", "%B %d %Y",
        "%b %d, %Y", "%b %d %Y",
        "%Y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# ------------------------------------------------------------------- IO


def _extract_pdf_text(pdf_path: str | Path) -> str:
    """Open the PDF with pdfplumber and concatenate every page's text."""
    try:
        import pdfplumber                                # type: ignore
    except ImportError as e:
        raise RuntimeError("pdfplumber not installed; add to pyproject deps.") from e

    parts: list[str] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            txt = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
            parts.append(txt)
    return "\n".join(parts)


# ------------------------------------------------------------------- Parser


class PdfOMParser(Parser):
    source_id = "pdf_om"

    def parse(self, message: EmailMessage) -> ParseResult:
        all_listings: list[Listing] = []
        all_warnings: list[str] = []
        confidences: list[float] = []

        for att in (message.attachments or []):
            if att.mime_type != "application/pdf":
                continue
            if not att.local_path:
                all_warnings.append(f"{att.filename}: no local_path (download skipped)")
                continue
            r = self.parse_pdf(att.local_path, email_id=message.id)
            all_listings.extend(r.listings)
            all_warnings.extend(r.warnings)
            confidences.append(r.extraction_confidence)

        confidence = sum(confidences) / len(confidences) if confidences else 0.0
        return ParseResult(
            listings=all_listings,
            warnings=all_warnings,
            extraction_confidence=round(confidence, 2),
        )

    def parse_pdf(self, pdf_path: str | Path, *, email_id: str = "",
                  channel: str = "") -> ParseResult:
        try:
            text = _extract_pdf_text(pdf_path)
        except Exception as e:                          # noqa: BLE001
            log.warning("pdf.extract_failed", path=str(pdf_path), error=str(e))
            return ParseResult(
                listings=[], warnings=[f"PDF extract failed: {e}"],
                extraction_confidence=0.0,
            )
        _listing, result = extract_from_text(
            text, source="pdf_om", email_id=email_id, channel=channel,
        )
        return result
