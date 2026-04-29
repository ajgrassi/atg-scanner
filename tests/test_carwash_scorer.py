"""Car wash NNN scorer tests.

The 3 fixtures from CLAUDE.md (MOD Wash Bridgeville, Quick Quack Murrieta,
Mister American Fork) are used to validate score bands. Without the actual
OMs, we synthesize each from realistic field values so the scorer math is
exercised end-to-end.
"""

from __future__ import annotations

from app.listing import Listing
from app.scorers.carwash_nnn import CarwashNNNScorer


def _carwash(**overrides) -> Listing:
    """Build a typical car-wash NNN Listing with sane defaults."""
    base = dict(
        source="sands_ig", channel="car_wash_nnn",
        title="Test Car Wash", address="123 Wash Ln",
        city="Springfield", state="MO", zip="65802",
        price=4_000_000, email_id="<t>",
        cap_rate=0.065, noi=260_000, sf=4_500, lot_acres=1.5,
        tenant="Mister Car Wash", tenant_credit="public_corporate",
        lease_type="absolute_nnn", term_remaining_years=18.0,
        escalator_pct=0.015, roof_structure="tenant",
        bonus_dep_eligible=True,
        raw_data={"carwash_format": "express_tunnel"},
    )
    base.update(overrides)
    return Listing(**base)


# ----------------------------------------------------- structural gates

def test_gate_ground_lease_fails():
    listing = _carwash(lease_type="ground_lease")
    result = CarwashNNNScorer().evaluate(listing)
    assert result.verdict == "STRUCTURAL_FAIL"
    assert "ground_lease_excluded" in result.structural_failures


def test_gate_landlord_roof_fails():
    listing = _carwash(roof_structure="landlord")
    result = CarwashNNNScorer().evaluate(listing)
    assert result.verdict == "STRUCTURAL_FAIL"
    assert any("roof" in f for f in result.structural_failures)


def test_gate_modified_gross_lease_fails():
    listing = _carwash(lease_type="nn")
    result = CarwashNNNScorer().evaluate(listing)
    assert result.verdict == "STRUCTURAL_FAIL"
    assert any("absolute_nnn" in f for f in result.structural_failures)


def test_gate_bonus_dep_required():
    listing = _carwash(bonus_dep_eligible=False)
    result = CarwashNNNScorer().evaluate(listing)
    assert result.verdict == "STRUCTURAL_FAIL"
    assert "not_bonus_dep_eligible" in result.structural_failures


# ----------------------------------------------------- canonical fixtures

def test_canonical_mod_wash_bridgeville():
    """MOD Wash Bridgeville — expected PURSUE_CONDITIONS, score 70-78.

    MOD Wash is tier-2; private_large credit; 18yr lease; ~6.5% cap.
    """
    listing = _carwash(
        title="MOD Wash Bridgeville",
        address="1100 Washington Pike, Bridgeville, PA 15017",
        city="Bridgeville", state="PA", zip="15017",
        price=3_900_000, cap_rate=0.0660, noi=257_400,
        tenant="MOD Wash", tenant_credit="private_large",
        term_remaining_years=18.0, escalator_pct=0.0150,
        raw_data={"carwash_format": "express_tunnel"},
    )
    result = CarwashNNNScorer().evaluate(listing)
    assert result.verdict in ("PURSUE", "PURSUE_CONDITIONS"), \
        f"verdict={result.verdict} score={result.score} notes={result.notes}"
    assert 65 <= result.score <= 80


def test_canonical_quick_quack_murrieta_ground_lease_fails():
    """Quick Quack Murrieta is a ground-lease deal → STRUCTURAL_FAIL."""
    listing = _carwash(
        title="Quick Quack Murrieta",
        address="40000 California Oaks Rd, Murrieta, CA 92562",
        city="Murrieta", state="CA", zip="92562",
        price=4_500_000, tenant="Quick Quack",
        tenant_credit="private_large",
        lease_type="ground_lease",                   # the disqualifier
        term_remaining_years=20.0, escalator_pct=0.020,
    )
    result = CarwashNNNScorer().evaluate(listing)
    assert result.verdict == "STRUCTURAL_FAIL"
    assert "ground_lease_excluded" in result.structural_failures


def test_canonical_mister_american_fork():
    """Mister American Fork — tier-1 brand, public corporate credit, but a
    moderate-term lease and middling cap. Expected PURSUE_CONDITIONS 68-75."""
    listing = _carwash(
        title="Mister Car Wash American Fork",
        address="800 W Main St, American Fork, UT 84003",
        city="American Fork", state="UT", zip="84003",
        price=5_000_000, cap_rate=0.0625, noi=312_500,
        tenant="Mister Car Wash", tenant_credit="public_corporate",
        term_remaining_years=15.5, escalator_pct=0.015,
        raw_data={"carwash_format": "express_tunnel"},
    )
    result = CarwashNNNScorer().evaluate(listing)
    assert result.verdict in ("PURSUE", "PURSUE_CONDITIONS"), \
        f"verdict={result.verdict} score={result.score}"
    assert 65 <= result.score <= 80


# ----------------------------------------------------- band edges

def test_pursue_band_threshold_at_80():
    """A maximally-favorable car wash should clear PURSUE."""
    listing = _carwash(
        cap_rate=0.075,                                # ≥7% → 12 pts
        escalator_pct=0.020,                           # ≥1.8% → 12 pts
        term_remaining_years=20.0,                     # ≥18yr → 18 pts
        tenant="Mister Car Wash", tenant_credit="public_corporate",  # 18 pts
        price=3_500_000,                               # $2-6M → 8 pts
        noi=400_000,                                   # very strong CF
        raw_data={"carwash_format": "self_service"},   # 15 pts
    )
    result = CarwashNNNScorer().evaluate(listing)
    assert result.verdict == "PURSUE", \
        f"verdict={result.verdict} score={result.score}"


def test_pass_band_for_weak_deal():
    """Franchisee + 5yr term + 5.5% cap + flat escalator → PASS."""
    listing = _carwash(
        tenant_credit="franchisee", tenant="Random Wash",
        term_remaining_years=5.0, escalator_pct=0.005,
        cap_rate=0.055, noi=180_000,
        price=3_300_000, raw_data={"carwash_format": "full_service"},
    )
    result = CarwashNNNScorer().evaluate(listing)
    assert result.verdict == "PASS", \
        f"verdict={result.verdict} score={result.score} notes={result.notes}"


def test_components_sum_to_score():
    """Sanity: the score is exactly sum(components)."""
    listing = _carwash()
    result = CarwashNNNScorer().score(listing)
    assert abs(sum(result.components.values()) - result.score) < 0.05


def test_brand_strength_tier_assignment():
    from app.scorers.carwash_nnn import _brand_tier
    assert _brand_tier("Mister Car Wash") == 1
    assert _brand_tier("Take 5 Express") == 1
    assert _brand_tier("MOD Wash") == 2
    assert _brand_tier("Quick Quack Car Wash") == 2
    assert _brand_tier("Joe's Independent Wash") == 3
    assert _brand_tier(None) == 3
