"""Car wash NNN scorer — full weighted math.

Per CLAUDE.md § Channel: car_wash_nnn:

Structural gates (all must pass; any fail → STRUCTURAL_FAIL):
  1. lease_type == "absolute_nnn"
  2. bonus_dep_eligible == True
  3. roof_structure == "tenant"
  4. lease_type != "ground_lease"

Weighted score (0–100) with 8 components:
  Tenant credit (18), Lease term remaining (18), Cost seg potential (15),
  Cap rate vs market (12), Rent escalator (12), Y1 cash flow (10),
  Deal size fit (8), Brand strength (7).

Verdict bands: ≥80 PURSUE, 65–79 PURSUE_CONDITIONS, 50–64 WATCH, <50 PASS.
"""

from __future__ import annotations

from ..listing import Listing, ScoreResult
from .base import Scorer


# Brand tiers per the v2 spec.
TIER_1_BRANDS = {
    "mister", "mister car wash",
    "take 5", "take5",
    "whistle express", "whistle",
    "tidal wave", "tidal",
    "mammoth holdings", "mammoth",
    "whitewater express", "whitewater",
}
TIER_2_BRANDS = {
    "mod wash", "mod",
    "quick quack",
    "zips car wash", "zips",
    "club car wash", "club",
}


def _norm_brand(s: str | None) -> str:
    return (s or "").strip().lower()


def _brand_tier(tenant: str | None) -> int:
    t = _norm_brand(tenant)
    if not t:
        return 3
    if any(b in t for b in TIER_1_BRANDS):
        return 1
    if any(b in t for b in TIER_2_BRANDS):
        return 2
    return 3


def _annual_debt_service(price: float, *, down_pct: float = 0.25,
                         rate: float = 0.07, years: int = 25) -> float:
    """Standard 25/7/25-yr-am debt service — the assumption set used for
    all car-wash NNN cash-flow comparisons."""
    loan = price * (1 - down_pct)
    monthly_rate = rate / 12.0
    n = years * 12
    if monthly_rate == 0:
        return loan / years
    pmt = loan * (monthly_rate * (1 + monthly_rate) ** n) / ((1 + monthly_rate) ** n - 1)
    return pmt * 12


# ----------------------------------------------------------- component fns


def _component_tenant_credit(listing: Listing) -> tuple[float, str]:
    credit = listing.tenant_credit
    if credit == "public_corporate":
        return 18.0, "public_corporate=18"
    if credit == "private_large":
        return 14.0, "private_large=14"
    if credit == "private_small":
        return 8.0, "private_small=8"
    if credit == "franchisee":
        return 5.0, "franchisee=5"
    return 8.0, "unknown→private_small=8"


def _component_lease_term(listing: Listing) -> tuple[float, str]:
    yrs = listing.term_remaining_years or 0.0
    if yrs >= 18:
        return 18.0, f"{yrs}yr=18"
    if yrs >= 15:
        return 15.0, f"{yrs}yr=15"
    if yrs >= 10:
        return 8.0, f"{yrs}yr=8"
    if yrs >= 7:
        return 4.0, f"{yrs}yr=4"
    return 0.0, f"{yrs}yr=0"


def _component_cost_seg(listing: Listing) -> tuple[float, str]:
    """Heuristic from raw_data['carwash_format'] when known.

    Format keys (per CLAUDE.md): self_service, express_tunnel, tunnel_plus_light,
    full_service. Default = express_tunnel (most common).
    """
    fmt = ((listing.raw_data or {}).get("carwash_format") or "express_tunnel").lower()
    table = {
        "self_service":        (15.0, "self_service=15"),
        "express_tunnel":      (12.0, "express_tunnel=12"),
        "tunnel_plus_light":   (10.0, "tunnel_plus_light=10"),
        "full_service":        (8.0,  "full_service=8"),
    }
    return table.get(fmt, (12.0, f"{fmt}→default=12"))


def _component_cap_vs_market(listing: Listing) -> tuple[float, str]:
    cap = listing.cap_rate
    if cap is None:
        return 6.0, "cap_unknown→6"
    pct = cap * 100
    if pct >= 7.0:
        return 12.0, f"{pct:.1f}%≥7=12"
    if pct >= 6.5:
        return 9.0, f"{pct:.1f}%=9"
    if pct >= 6.0:
        return 6.0, f"{pct:.1f}%=6"
    return 3.0, f"{pct:.1f}%<6=3"


def _component_escalator(listing: Listing) -> tuple[float, str]:
    esc = listing.escalator_pct
    if esc is None:
        return 6.0, "escalator_unknown→6"
    pct = esc * 100
    if pct >= 1.8:
        return 12.0, f"{pct:.1f}%≥1.8=12"
    if pct >= 1.4:
        return 9.0, f"{pct:.1f}%=9"
    if pct >= 1.0:
        return 6.0, f"{pct:.1f}%=6"
    return 2.0, f"{pct:.1f}%<1=2"


def _component_y1_cash_flow(listing: Listing) -> tuple[float, str]:
    """Y1 cash flow assuming 25% down, 7% rate, 25-yr am."""
    if not listing.noi:
        return 5.0, "noi_unknown→5"
    ds = _annual_debt_service(float(listing.price))
    cf_monthly = (listing.noi - ds) / 12.0
    if cf_monthly >= 5_000:
        return 10.0, f"${cf_monthly:.0f}/mo≥5k=10"
    if cf_monthly >= 2_000:
        return 8.0, f"${cf_monthly:.0f}/mo=8"
    if cf_monthly >= 0:
        return 5.0, f"${cf_monthly:.0f}/mo=5"
    if cf_monthly >= -2_000:
        return 2.0, f"${cf_monthly:.0f}/mo=2"
    return 0.0, f"${cf_monthly:.0f}/mo<-2k=0"


def _component_deal_size(listing: Listing) -> tuple[float, str]:
    p = listing.price
    if 2_000_000 <= p <= 6_000_000:
        return 8.0, "$2-6M=8"
    if 1_500_000 <= p < 2_000_000 or 6_000_000 < p <= 8_000_000:
        return 6.0, f"${p:,}=6"
    return 3.0, f"${p:,}=3"


def _component_brand_strength(listing: Listing) -> tuple[float, str]:
    tier = _brand_tier(listing.tenant)
    table = {1: 7.0, 2: 5.0, 3: 3.0}
    return table[tier], f"tier{tier}={int(table[tier])}"


# ----------------------------------------------------------------- scorer


class CarwashNNNScorer(Scorer):
    channel = "car_wash_nnn"

    def structural_gates(self, listing: Listing) -> tuple[bool, list[str]]:
        failed: list[str] = []
        if listing.lease_type != "absolute_nnn":
            failed.append(f"lease_type={listing.lease_type}_not_absolute_nnn")
        if listing.bonus_dep_eligible is not True:
            failed.append("not_bonus_dep_eligible")
        if listing.roof_structure != "tenant":
            failed.append(f"roof={listing.roof_structure}_not_tenant")
        if listing.lease_type == "ground_lease":
            failed.append("ground_lease_excluded")
        return (not failed), failed

    def score(self, listing: Listing) -> ScoreResult:
        components: dict[str, float] = {}
        notes: list[str] = []

        def add(name: str, comp: tuple[float, str]) -> None:
            components[name] = comp[0]
            notes.append(f"{name}: {comp[1]}")

        add("tenant_credit",   _component_tenant_credit(listing))
        add("lease_term",      _component_lease_term(listing))
        add("cost_seg",        _component_cost_seg(listing))
        add("cap_vs_market",   _component_cap_vs_market(listing))
        add("escalator",       _component_escalator(listing))
        add("y1_cash_flow",    _component_y1_cash_flow(listing))
        add("deal_size",       _component_deal_size(listing))
        add("brand_strength",  _component_brand_strength(listing))

        score = sum(components.values())

        if score >= 80:
            verdict = "PURSUE"
        elif score >= 65:
            verdict = "PURSUE_CONDITIONS"
        elif score >= 50:
            verdict = "WATCH"
        else:
            verdict = "PASS"

        return ScoreResult(
            score=round(score, 1),
            verdict=verdict,                   # type: ignore[arg-type]
            components=components,
            notes=notes,
        )
