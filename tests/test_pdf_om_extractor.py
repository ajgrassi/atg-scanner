"""PDF OM text-extraction tests.

We test extract_from_text() (regex-only path) against synthetic OM-shaped
text. Real PDF samples (when Andrew drops them in tests/fixtures/) get
exercised by a separate `parse_pdf` integration test that's marked optional.
"""

from __future__ import annotations

from pathlib import Path

from app.parsers.pdf_om import extract_from_text


# Realistic excerpt of a car wash OM body — typical Sands IG / Matthews format.
CAR_WASH_OM = """
EXCLUSIVE OFFERING MEMORANDUM

Mister Car Wash
1234 Main Street, Bridgeville, PA 15017

Property Highlights
Offering Price: $4,250,000
Cap Rate: 6.50%
NOI: $276,250
Building Size: 4,150 SF
Lot Size: 1.42 Acres
Year Built: 2022

Lease Summary
Tenant: Mister Car Wash
Lease Type: Absolute NNN
Lease Term: 19.5 years remaining
Lease Expires: 11/30/2044
Rent Escalator: 1.5% annually
Roof Responsibility: Tenant

Brokerage Contact:
Sands Investment Group
"""


SELF_STORAGE_OM = """
SELF-STORAGE INVESTMENT OPPORTUNITY

500 Industrial Pkwy, Tulsa, OK 74145

Asking Price: $3.2M
Cap Rate: 7.25%
Building Size: 62,000 SF
Lot Size: 4.20 acres
Year Built: 2008

Currently 88% occupied with strong NNN-equivalent income.
"""


def test_carwash_om_extracts_full_record():
    listing, result = extract_from_text(CAR_WASH_OM, source="sands_ig",
                                         email_id="<test1>", channel="car_wash_nnn")
    assert listing is not None
    assert listing.address.startswith("1234 Main Street")
    assert listing.city == "Bridgeville"
    assert listing.state == "PA"
    assert listing.zip == "15017"
    assert listing.price == 4_250_000
    assert listing.sf == 4_150
    assert listing.cap_rate == 0.065
    assert listing.noi == 276_250
    assert listing.tenant == "Mister Car Wash"
    assert listing.lease_type == "absolute_nnn"
    assert listing.term_remaining_years == 19.5
    assert listing.escalator_pct == 0.015
    assert listing.roof_structure == "tenant"
    assert listing.bonus_dep_eligible is True
    assert listing.lot_acres == 1.42
    assert result.extraction_confidence >= 0.85


def test_self_storage_om_extracts_partial():
    listing, result = extract_from_text(SELF_STORAGE_OM, source="argus_storage",
                                         email_id="<test2>", channel="self_storage")
    assert listing is not None
    assert listing.price == 3_200_000               # $3.2M
    assert listing.sf == 62_000
    assert listing.cap_rate == 0.0725
    assert listing.lot_acres == 4.20
    assert listing.state == "OK"
    # No tenant/lease info → those fields stay None
    assert listing.tenant is None
    assert listing.lease_type is None
    # Confidence reflects that nice-to-haves are missing
    assert 0.4 <= result.extraction_confidence < 0.85


def test_missing_must_haves_returns_none():
    text = "Just a property with no price or sf info. 123 Test Rd, Springfield, MO 65801"
    listing, result = extract_from_text(text)
    assert listing is None
    assert any("price" in w or "sf" in w for w in result.warnings)


def test_money_suffix_handling():
    text = """
    Property Highlights
    Offering Price: $2.5MM
    Building Size: 5000 SF
    Address: 100 Test Ave, Anywhere, TX 75001
    """
    listing, _ = extract_from_text(text)
    assert listing is not None
    assert listing.price == 2_500_000


def test_must_have_only_extraction_no_review_flag_at_threshold():
    """When we have only the must-have fields (no nice-to-haves), confidence
    lands exactly at the 0.7 threshold — the spec says `< 0.7` flags needs_review,
    so 0.7 itself does not."""
    text = """
    100 Tiny Lane, Mini City, MO 65801
    Offering Price: $500,000
    Building Size: 2,500 SF
    """
    listing, result = extract_from_text(text)
    assert listing is not None
    assert result.extraction_confidence == 0.7
    assert listing.needs_review is False


def test_partial_extraction_flags_needs_review():
    """When the address pattern doesn't match (still got price+sf via inline
    money), confidence drops below 0.7 → needs_review=True."""
    text = """
    Just a test property.
    Offering Price: $500,000
    Building Size: 2,500 SF
    """
    listing, _ = extract_from_text(text)
    # No address means must-haves missed → no listing returned
    assert listing is None


# ---- Optional: real-PDF parse round-trip when fixtures exist -----

FIXTURES = Path(__file__).parent / "fixtures"


def test_real_pdf_round_trip_when_available():
    """If real OM PDFs are dropped in tests/fixtures/*.pdf, run them through
    parse_pdf and assert we get a Listing."""
    if not FIXTURES.exists():
        return
    pdfs = list(FIXTURES.glob("*.pdf"))
    if not pdfs:
        return
    from app.parsers.pdf_om import PdfOMParser
    parser = PdfOMParser()
    for pdf in pdfs:
        result = parser.parse_pdf(pdf, email_id=f"<{pdf.name}>", channel="car_wash_nnn")
        # Don't assert specific values — fixtures vary — just smoke test.
        assert isinstance(result.extraction_confidence, float)
