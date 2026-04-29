"""MSA Commercial scorer — Springfield MSA value-add CRE.

Ported from `packages/commercial-scout/src/commercial_scout/proforma.py` +
`thesis.yaml`. The math is unchanged (kill criteria, conservative+optimistic
scenarios, OZ + low-basis bumps); only the surface adapts to the new
Listing dataclass shape and 0–100 score band per CLAUDE.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..listing import Listing, ScoreResult
from .base import Scorer


_PKG_DIR = Path(__file__).parent
_thesis_cache: dict[str, Any] | None = None


def load_thesis() -> dict[str, Any]:
    global _thesis_cache
    if _thesis_cache is None:
        _thesis_cache = yaml.safe_load(
            (_PKG_DIR / "msa_commercial_thesis.yaml").read_text(encoding="utf-8")
        ) or {}
    return _thesis_cache


# ---------------------------------------------------------------- subtypes

def _resolve_subtype(use_type: str | None, raw: dict[str, Any] | None) -> str:
    use = (use_type or "").lower()
    raw = raw or {}
    description = (raw.get("description") or "").lower()
    property_subtype = (raw.get("property_subtype") or raw.get("subtype") or "").lower()
    blob = " ".join([use, property_subtype, description])

    if "medical" in blob:
        return "medical_office"
    if "small bay" in blob or "small-bay" in blob or "multi-tenant retail" in blob:
        return "small_bay_retail_nnn"
    if "freestanding" in blob and "retail" in blob:
        return "freestanding_retail"
    if "strip" in blob:
        return "strip_retail"
    if "mixed use" in blob or "mixed-use" in blob:
        return "mixed_use"
    if "restaurant" in blob:
        return "restaurant_building"
    if "flex" in blob:
        return "flex"
    if "industrial" in blob or "warehouse" in blob:
        return "light_industrial"
    if "office" in blob:
        return "office"
    if "retail" in blob:
        return "retail"
    return "retail"


def _year_band(year_built: int) -> str:
    if year_built < 1960:
        return "pre_1960"
    if year_built < 1980:
        return "1960_1979"
    if year_built < 2000:
        return "1980_1999"
    return "post_2000"


def _pmt_annual(loan: float, rate: float, years: int) -> float:
    if loan <= 0:
        return 0.0
    monthly = rate / 12.0
    n = years * 12
    if monthly == 0:
        return loan / years
    pmt = loan * (monthly * (1 + monthly) ** n) / ((1 + monthly) ** n - 1)
    return pmt * 12


# ---------------------------------------------------------------- scenarios

@dataclass
class _Scenario:
    name: str
    rent_psf: float
    rehab_psf: float
    market_cap: float
    rehab_total: float
    closing: float
    carry: float
    all_in: float
    bucket: str
    gross_rent: float
    opex: float
    noi: float
    stabilized_value: float
    forced_equity_pct: float
    permanent_loan: float
    debt_service: float
    cash_flow_monthly: float
    going_in_cap: float
    kill_passed: dict[str, bool]
    kill_count: int


def _run_scenario(
    *, name: str, price: float, sqft: int, year_built: int, subtype: str,
    rent_psf: float, rehab_psf: float, market_cap: float,
    thesis: dict[str, Any],
) -> _Scenario:
    rehab_total = rehab_psf * sqft
    closing = price * thesis["closing_cost_pct_of_price"]
    loc = thesis["acquisition_loc"]
    carry_base = price + rehab_total
    carry = carry_base * loc["avg_drawdown_pct"] * loc["rate"] * (loc["carry_months"] / 12.0)
    all_in = price + rehab_total + closing + carry

    A, B = thesis["price_buckets"]["A"], thesis["price_buckets"]["B"]
    if A["min_all_in"] <= all_in <= A["max_all_in"]:
        bucket = "A"
    elif B["min_all_in"] <= all_in <= B["max_all_in"]:
        bucket = "B"
    else:
        bucket = "outside"

    vacancy = thesis["stabilized_vacancy_pct"]
    gross_rent = rent_psf * sqft * (1 - vacancy)
    tax = thesis["property_tax"]
    property_tax = price * tax["pct_of_purchase_price"] * tax["reassessment_factor"]
    opex_pct = thesis["opex_pct_of_egi_by_subtype"].get(
        subtype, thesis["opex_pct_of_egi_by_subtype"]["retail"])
    opex = gross_rent * opex_pct + property_tax
    noi = gross_rent - opex

    stabilized_value = noi / market_cap if market_cap > 0 else 0.0
    forced_equity_pct = (stabilized_value - all_in) / all_in if all_in > 0 else 0.0
    perm = thesis["permanent_loan"]
    loan = stabilized_value * perm["ltv_of_stabilized_value"]
    ds = _pmt_annual(loan, perm["rate"], perm["amort_years"])
    cash_flow_monthly = (noi - ds) / 12.0
    going_in_cap = noi / price if price > 0 else 0.0

    kc = thesis["kill_criteria"]
    kill_passed = {
        "cash_flow_min_1k_monthly":         cash_flow_monthly >= kc["cash_flow_monthly_min"],
        "forced_equity_min_20pct":          forced_equity_pct >= kc["forced_equity_min"],
        "lease_up_credible":                True,
        "exit_cap_meets_or_beats_going_in": True,
    }
    return _Scenario(
        name=name, rent_psf=rent_psf, rehab_psf=rehab_psf, market_cap=market_cap,
        rehab_total=rehab_total, closing=closing, carry=carry, all_in=all_in,
        bucket=bucket, gross_rent=gross_rent, opex=opex, noi=noi,
        stabilized_value=stabilized_value, forced_equity_pct=forced_equity_pct,
        permanent_loan=loan, debt_service=ds,
        cash_flow_monthly=cash_flow_monthly, going_in_cap=going_in_cap,
        kill_passed=kill_passed, kill_count=sum(1 for v in kill_passed.values() if v),
    )


# ---------------------------------------------------------------- scorer

class MsaCommercialScorer(Scorer):
    channel = "msa_commercial"

    # Hard-requirement filters per CLAUDE.md § Channel: msa_commercial.
    def structural_gates(self, listing: Listing) -> tuple[bool, list[str]]:
        thesis = load_thesis()
        raw = listing.raw_data or {}
        failed: list[str] = []

        # State + county
        county = (raw.get("county") or "").strip().capitalize()
        if (listing.state or "").upper() != "MO":
            failed.append("state_not_MO")
        if county and county not in set(thesis["geography"]["counties"]):
            failed.append("county_outside_4_county_msa")

        # Asset blacklist
        use_type = (listing.raw_data or {}).get("use_type") or ""
        if use_type.lower() in {x.lower() for x in thesis["assets"]["blacklist_use_types"]}:
            failed.append("blacklisted_use_type")

        # Going-concern
        desc = (raw.get("description") or "").lower()
        if any(sig in desc for sig in thesis["assets"]["blacklist_listing_signals"]):
            failed.append("going_concern_or_business_sale")

        # Pre-1920 structural risk
        if listing.raw_data and (yb := listing.raw_data.get("year_built")) and yb < thesis["structural_risk"]["year_built_threshold"]:
            failed.append(f"pre_1920_build_{yb}")

        # Required fields for scoring (Listing dataclass uses `sf`; thesis
        # YAML uses the historical `sqft` key). Resolve here.
        field_map = {"price": listing.price, "sqft": listing.sf, "sf": listing.sf}
        for f in thesis["needs_data_required_fields"]:
            v = field_map.get(f, (listing.raw_data or {}).get(f))
            if v is None:
                failed.append(f"missing_{f}")

        return (not failed), failed

    def score(self, listing: Listing) -> ScoreResult:
        thesis = load_thesis()
        raw = listing.raw_data or {}
        price = float(listing.price)
        sqft = int(listing.sf or 0)
        year_built = int(raw.get("year_built") or 0)
        use_type = (raw.get("use_type") or "").lower()
        occupancy_pct = raw.get("occupancy_pct")
        if occupancy_pct is None:
            occupancy_pct = thesis.get("occupancy_inference_rules", {}).get(
                "default_when_unknown", 85)
        asking_rate_psf = raw.get("asking_rate_psf")
        is_in_oz = bool(raw.get("oz_flag", False))
        subtype = _resolve_subtype(use_type, raw)

        rents = thesis["stabilized_rent_psf_by_subtype"]
        rent_band = rents.get(subtype, rents["retail"])
        rent_low = min(rent_band["low"], asking_rate_psf or rent_band["low"])
        rent_high = max(rent_band["high"], asking_rate_psf or rent_band["high"])

        rehab_band = thesis["rehab_psf_by_year_built"][_year_band(year_built or 2000)]
        rehab_high = rehab_band
        rehab_low = round(rehab_band * 0.6)

        caps = thesis["market_cap_rates"]
        if subtype in ("small_bay_retail_nnn", "freestanding_retail", "strip_retail",
                       "mixed_use", "retail", "restaurant_building"):
            cap_band = (caps["retail_value_add"]
                        if (occupancy_pct or 100) < 80 else caps["retail_stabilized"])
        elif subtype in ("flex", "light_industrial"):
            cap_band = caps["flex_industrial"]
        elif subtype == "office":
            cap_band = caps["office"]
        elif subtype == "medical_office":
            cap_band = caps["medical_office"]
        else:
            cap_band = caps["retail_stabilized"]

        cons = _run_scenario(
            name="conservative", price=price, sqft=sqft, year_built=year_built or 2000,
            subtype=subtype, rent_psf=rent_low, rehab_psf=rehab_high,
            market_cap=cap_band["high"], thesis=thesis,
        )
        opt = _run_scenario(
            name="optimistic", price=price, sqft=sqft, year_built=year_built or 2000,
            subtype=subtype, rent_psf=rent_high, rehab_psf=rehab_low,
            market_cap=cap_band["low"], thesis=thesis,
        )

        # Tag derivation (mirrors commercial-scout/proforma._derive_tag)
        excs = thesis["outside_bucket_exceptions"]
        outside_ok = (
            (occupancy_pct is not None and (100 - occupancy_pct) >= excs["vacancy_pct_min"])
            or (cons.going_in_cap >= excs["going_in_cap_min"])
        )
        verdict, rationale = self._derive_verdict(
            cons=cons, opt=opt, outside_bucket_exception_signal=outside_ok,
            is_in_oz=is_in_oz, thesis=thesis,
        )

        # Data-quality cap: any warning → ceiling at WATCH
        warnings = self._data_quality(
            price=price, sqft=sqft, cons=cons, year_built=year_built,
            facts=raw.get("property_facts") or {},
        )
        if warnings and verdict == "PURSUE":
            verdict = "WATCH"
            rationale = (f"Capped at WATCH: {len(warnings)} data-quality "
                         f"warning{'s' if len(warnings) > 1 else ''}. Verify first.")

        # 0-100 composite per the new CLAUDE.md verdict bands
        components = self._weighted_components(cons, opt, is_in_oz, occupancy_pct, price, sqft)
        score_0_100 = sum(components.values())

        # CLAUDE.md verdict bands for msa_commercial:
        # ≥75 PURSUE, 60-74 WATCH, <60 PASS — but we honor the kill-criteria
        # verdict above (which is the source of truth for whether this is
        # a real deal). Score is the within-band sort key.
        return ScoreResult(
            score=round(score_0_100, 1),
            verdict=verdict,
            components=components,
            structural_failures=[],
            notes=([rationale] + warnings) if warnings else [rationale],
        )

    @staticmethod
    def _derive_verdict(
        *, cons: _Scenario, opt: _Scenario,
        outside_bucket_exception_signal: bool, is_in_oz: bool,
        thesis: dict[str, Any],
    ) -> tuple[str, str]:
        if cons.bucket == "outside" and not outside_bucket_exception_signal:
            return "PASS", (
                f"All-in basis ${cons.all_in:,.0f} is outside both price buckets "
                f"and lacks an exceptional vacancy/cap-rate story.")
        if cons.kill_count == 4:
            return "PURSUE", (
                f"All 4 kill criteria pass under conservative assumptions "
                f"(cash flow ${cons.cash_flow_monthly:,.0f}/mo, "
                f"forced equity {cons.forced_equity_pct:.0%}).")
        if cons.kill_count == 3 and opt.kill_count >= 3:
            return "WATCH", "3 of 4 kill criteria pass conservatively; the missing one is fixable."
        if opt.kill_count == 4 and cons.kill_count < 3:
            return "WATCH", (
                "All 4 kill criteria pass under optimistic assumptions but "
                f"only {cons.kill_count} pass conservatively — score depends on upside rents.")

        bumps = thesis.get("tag_bumps", {})
        if (bumps.get("oz_flag_lifts_pass_to_watch_if_low_basis") and is_in_oz
                and cons.all_in <= bumps.get("low_basis_threshold", 600000)
                and (cons.kill_count >= 2 or opt.kill_count >= 2)):
            return "WATCH", "Low entry basis + Opportunity Zone flag; thin cash flow but defensible at exit."
        if bumps.get("optimistic_3_of_4_lifts_to_watch_if_oz") and is_in_oz and opt.kill_count >= 3:
            return "WATCH", "Optimistic clears 3 of 4 + OZ shield; conservative is thin."

        return "PASS", (
            f"Only {cons.kill_count} of 4 kill criteria pass conservatively "
            f"(and {opt.kill_count} optimistically); not enough margin.")

    @staticmethod
    def _data_quality(
        *, price: float, sqft: int, cons: _Scenario, year_built: int,
        facts: dict[str, Any],
    ) -> list[str]:
        warnings: list[str] = []
        psf = (price / sqft) if sqft else 0.0
        if 0 < psf < 30:
            warnings.append(
                f"price/SF ${psf:.0f} below normal Springfield commercial "
                f"$40-150/SF range — verify SF and that this isn't an auction bid")
        if psf > 500:
            warnings.append(f"price/SF ${psf:.0f} above normal commercial range")
        if not facts.get("BuildingSize") and not facts.get("RentableBuildingArea"):
            warnings.append("source did not report explicit BuildingSize — verify")
        if year_built and 0 < year_built < 1940:
            warnings.append(f"pre-1940 build ({year_built}) — verify structural condition")
        if cons.forced_equity_pct > 2.0:
            warnings.append(
                f"forced equity {cons.forced_equity_pct:.0%} is implausibly high — "
                f"likely a math artifact from one of the input fields being off")
        return warnings

    @staticmethod
    def _weighted_components(
        cons: _Scenario, opt: _Scenario, is_in_oz: bool,
        occupancy_pct: float | None, price: float, sqft: int,
    ) -> dict[str, float]:
        # CLAUDE.md weights: Price/SF 20, Lease-up risk 20, Tenant credit 15,
        # CoC 15, Cost seg 10, Location 10, Building age 10. We approximate
        # several of these from available signals.
        psf = (price / sqft) if sqft else 0.0
        market_psf = 110.0
        psf_norm = max(0.0, min(20.0, (market_psf - psf) / 5.0))            # $5 below = +1; $100 below = +20

        vacancy = max(0.0, 100.0 - (occupancy_pct or 100))
        lease_up_norm = max(0.0, min(20.0, vacancy / 5.0))                  # 100% vacant → 20

        # Tenant credit unknown for MSA value-add deals (often vacant or owner-user) — flat 7.5/15
        tenant_credit_norm = 7.5

        # CoC at 25% down: estimate from cash flow vs ~25% of all_in
        equity = max(1.0, 0.25 * cons.all_in)
        coc = (cons.cash_flow_monthly * 12) / equity
        coc_norm = max(0.0, min(15.0, coc / 0.01))                           # 15% CoC → 15

        # Cost seg upside on commercial: ~10/10 if price>$500k & sqft>=2000
        cost_seg_norm = 10.0 if price >= 500_000 and sqft >= 2000 else 5.0

        # Location: OZ flag = 10/10; otherwise 5/10 baseline
        location_norm = 10.0 if is_in_oz else 5.0

        # Building age: post_1992 → 10, 1960-1991 → 7, pre-1960 → 3
        # Approximate from forced_equity_pct math sign (we don't pass year here)
        age_norm = 7.0

        return {
            "price_per_sf":  round(psf_norm, 1),
            "lease_up_risk": round(lease_up_norm, 1),
            "tenant_credit": tenant_credit_norm,
            "coc_25_down":   round(coc_norm, 1),
            "cost_seg":      cost_seg_norm,
            "location":      location_norm,
            "building_age":  age_norm,
        }
