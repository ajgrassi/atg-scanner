"""MSA Commercial scorer tests — the 3 canonical Springfield listings.

These are the same fixtures the commercial-scout package validated against.
The scorer's tag derivation is identical; only the surrounding wrapper changed.

  1. 5540 N Farmer Branch Rd, Ozark — $1.55M, 12,728 SF, 2008, 75% vacant
     → WATCH or PURSUE depending on rents
  2. 532 E Walnut St, Springfield — $385k, 3,848 SF, 1960, OZ
     → WATCH (thin cash flow, OZ + low entry)
  3. 111 W Main, Ash Grove — $495k, 8,335 SF, 1898, restaurant going-concern
     → STRUCTURAL_FAIL or PASS-equivalent
"""

from __future__ import annotations

from app.listing import Listing
from app.scorers.msa_commercial import MsaCommercialScorer


def _l(**raw_overrides) -> Listing:
    raw = {
        "use_type": raw_overrides.pop("use_type", "retail"),
        "year_built": raw_overrides.pop("year_built", 2000),
        "occupancy_pct": raw_overrides.pop("occupancy_pct", 85.0),
        "asking_rate_psf": raw_overrides.pop("asking_rate_psf", 18.0),
        "county": raw_overrides.pop("county", "Greene"),
        "oz_flag": raw_overrides.pop("oz_flag", False),
        "description": raw_overrides.pop("description", ""),
        "property_subtype": raw_overrides.pop("property_subtype", None),
        "property_facts": raw_overrides.pop("property_facts", {"BuildingSize": "x"}),
    }
    return Listing(
        source="test", channel="msa_commercial", title="t",
        address=raw_overrides.pop("address", "100 Main St"),
        city=raw_overrides.pop("city", "Springfield"),
        state=raw_overrides.pop("state", "MO"),
        zip=raw_overrides.pop("zip", "65801"),
        price=raw_overrides.pop("price", 600_000),
        sf=raw_overrides.pop("sqft", raw_overrides.pop("sf", 5_000)),
        email_id="<t>",
        raw_data=raw,
    )


def test_canonical_5540_farmer_branch_ozark():
    listing = _l(
        address="5540 N Farmer Branch Rd, Ozark, MO 65721", city="Ozark",
        state="MO", zip="65721", price=1_550_000, sqft=12_728,
        year_built=2008, county="Christian",
        property_subtype="small bay", occupancy_pct=25.0, asking_rate_psf=18.0,
        description="Multi-tenant retail / flex small-bay. 75% vacant. Below market rents.",
    )
    result = MsaCommercialScorer().evaluate(listing)
    assert result.verdict in ("WATCH", "PURSUE"), \
        f"expected WATCH or PURSUE, got {result.verdict}: {result.notes}"


def test_canonical_532_walnut_springfield_oz():
    listing = _l(
        address="532 E Walnut St, Springfield, MO 65806", zip="65806",
        price=385_000, sqft=3_848, year_built=1960, county="Greene",
        property_subtype="small bay", occupancy_pct=85.0, asking_rate_psf=18.0,
        oz_flag=True,
        description="Downtown small-bay retail/office building. Opportunity Zone.",
    )
    result = MsaCommercialScorer().evaluate(listing)
    assert result.verdict == "WATCH", \
        f"expected WATCH, got {result.verdict}: {result.notes}"


def test_canonical_111_w_main_ash_grove_going_concern():
    listing = _l(
        address="111 W Main St, Ash Grove, MO 65604", city="Ash Grove",
        zip="65604", price=495_000, sqft=8_335, year_built=1898, county="Greene",
        use_type="restaurant", occupancy_pct=100.0, asking_rate_psf=12.0,
        description=("Turnkey restaurant business + real estate. Going concern. "
                     "All inventory included. Liquor license included."),
    )
    result = MsaCommercialScorer().evaluate(listing)
    # Both structural fail (pre-1920 + going-concern) reach the gate;
    # the gate fires before the scenario math runs.
    assert result.verdict == "STRUCTURAL_FAIL", \
        f"expected STRUCTURAL_FAIL, got {result.verdict}: {result.notes}"
    assert any("1920" in s or "going_concern" in s
               for s in result.structural_failures), result.structural_failures


def test_blacklisted_use_type_fails_gates():
    listing = _l(
        use_type="hospitality",
        price=500_000, sqft=5_000, year_built=1995, county="Taney",
    )
    result = MsaCommercialScorer().evaluate(listing)
    assert result.verdict == "STRUCTURAL_FAIL"
    assert "blacklisted_use_type" in result.structural_failures


def test_outside_4_county_fails_gates():
    listing = _l(
        address="789 Out Of Bounds Rd, Joplin, MO", city="Joplin",
        county="Jasper", price=600_000, sqft=5_000, year_built=2005,
    )
    result = MsaCommercialScorer().evaluate(listing)
    assert result.verdict == "STRUCTURAL_FAIL"
    assert "county_outside_4_county_msa" in result.structural_failures


def test_data_quality_caps_pursue_to_watch():
    """A listing that would otherwise PURSUE but has a data-quality warning
    (PSF below normal commercial range) gets capped at WATCH."""
    listing = _l(
        address="2222 Ridge Rd, Springfield, MO 65803", price=200_000,
        sqft=20_000,                                # $10/SF → flag
        year_built=2010, county="Greene", occupancy_pct=25.0, asking_rate_psf=18.0,
        property_subtype="small bay",
        description="50% vacant — strong value-add story.",
        property_facts={},                          # no BuildingSize → flag
    )
    result = MsaCommercialScorer().evaluate(listing)
    assert result.verdict == "WATCH", \
        f"expected WATCH (cap), got {result.verdict}: {result.notes}"
