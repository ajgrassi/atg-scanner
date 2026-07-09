"""ATG Deal Scanner — live run 2026-07-09.

Gmail MCP returned 3 threads (newer_than:1d) — all from Hanley Investment Group.
Hanley broker blasts don't include full street addresses (city/state headers only),
so the generic parser can't extract them. Listings are hand-constructed here from
the email body content with appropriate confidence scores.

Threads:
  19f438bf9913eff5 — Dutch Bros, Bridgeton MO        (car_wash_nnn, 5.65% cap)
  19f431b3b9c3e5f5 — Quick Quack Car Wash, Anaheim CA (car_wash_nnn, GROUND LEASE → STRUCTURAL_FAIL)
  19f42b04ba6a71a7 — Valvoline + Grocery Outlet, Wasco CA (car_wash_nnn, two listings)

Usage: uv run python run_live_20260709.py
Writes: data/draft_request.json  (if digest warranted)
        data/run_log.json         (appended)
"""

from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

from app import db, pipeline
from app.digest import Digest, DigestRow, PriceDropRow, ScanStats, build_draft
from app.gmail_client import DraftRequest, EmailMessage
from app.listing import Listing
from app.scorers import get_scorer
from app.utils import configure_logging, get_logger, utc_now

configure_logging()
log = get_logger("run_live_20260709")

# ── Escalator helper ──────────────────────────────────────────────────────────
# "10% increases every 5 years" → compound annual equivalent
_ESC_10PCT_5YR = round(math.pow(1.10, 1 / 5) - 1, 5)  # ≈ 0.01923 (1.923%/yr)


# ── Hand-constructed Listings ─────────────────────────────────────────────────
# Extraction notes:
#  - city/state from email header; no street number available
#  - price/cap/term from email body text
#  - tenant_credit manually assigned from public ticker info
#  - roof_structure="tenant" inferred from "zero landlord responsibilities" language
#  - bonus_dep_eligible=True for new-construction absolute NNN (standard underwriting)
#  - extraction_confidence lowered for missing fields (SF, zip, address number)

_NOW = utc_now()

LISTINGS: list[Listing] = [
    # ── 1. Dutch Bros — Bridgeton, MO ────────────────────────────────────────
    # Subject: "Now Available: New Dutch Bros; 15-Year Absolute NNN Corporate Lease"
    # NOTE: Dutch Bros is a coffee drive-thru, not a car wash. Hanley routes all
    # their listings to car_wash_nnn by domain. It passes structural gates (absolute
    # NNN, new construction, zero landlord) and is included for Andrew's awareness.
    Listing(
        source="hanley",
        source_listing_id="EPg000007R1C5",
        channel="car_wash_nnn",
        listing_url="https://hanleyinvestmentgroup.com/listings/?id=EPg000007R1C5",
        email_id="19f438bf9913eff5",
        title="Dutch Bros Drive-Thru — Bridgeton, MO",
        address="Saint Charles Rock Road, Bridgeton, MO",   # no street number in email
        city="Bridgeton",
        state="MO",
        zip=None,
        price=2_956_000,
        cap_rate=0.0565,
        noi=int(2_956_000 * 0.0565),                        # inferred from price × cap
        sf=None,                                             # not stated in email
        lot_acres=None,
        tenant="Dutch Bros",
        tenant_credit="public_corporate",                   # NYSE: BROS
        lease_type="absolute_nnn",
        lease_start=None,
        lease_expiration=None,
        term_remaining_years=15.0,
        escalator_pct=_ESC_10PCT_5YR,                       # 10% / 5yr compound annual
        roof_structure="tenant",                            # "zero landlord responsibilities"
        bonus_dep_eligible=True,                            # new construction
        estimated_cost_seg_pct=None,
        extraction_confidence=0.60,
        needs_review=True,
        raw_data={
            "extraction_method": "manual_20260709",
            "hanley_listing_id": "EPg000007R1C5",
            "broker_email_sender": "jlefko@hanleyinvestment.com",
            "broker_email_subject": "Now Available: New Dutch Bros; 15-Year Absolute NNN Corporate Lease, Dynamic Corner intersection",
            "notes": "Dutch Bros coffee drive-thru — not a car wash. Routed to car_wash_nnn by Hanley domain mapping. No street address in email. Address approximated from road name mentioned in body.",
            "brokers": ["Jeff Lefko <jlefko@hanleyinvestment.com> 844-585-7682",
                        "Bill Asher <basher@hanleyinvestment.com> 844-585-7684"],
        },
        first_seen=_NOW,
        last_seen=_NOW,
    ),

    # ── 2. Quick Quack Car Wash — Anaheim, CA ────────────────────────────────
    # Subject: "Just Listed: New Quick Quack Car Wash; Orange County, CA"
    # GROUND LEASE → STRUCTURAL_FAIL (same pattern as Quick Quack Murrieta in test fixtures)
    Listing(
        source="hanley",
        source_listing_id="EPg000009BJ8b",
        channel="car_wash_nnn",
        listing_url="https://hanleyinvestmentgroup.com/listings/?id=EPg000009BJ8b",
        email_id="19f431b3b9c3e5f5",
        title="Quick Quack Car Wash — Anaheim, CA (Ground Lease)",
        address="State College Blvd & E Underhill Ave, Anaheim, CA",
        city="Anaheim",
        state="CA",
        zip=None,
        price=3_882_000,
        cap_rate=None,
        noi=None,
        sf=None,
        lot_acres=None,
        tenant="Quick Quack Car Wash",
        tenant_credit="private_large",                      # 350+ locations, private
        lease_type="ground_lease",                          # explicit: "absolute NNN ground lease"
        lease_start=None,
        lease_expiration=None,
        term_remaining_years=16.0,                          # "16+ years remaining"
        escalator_pct=_ESC_10PCT_5YR,
        roof_structure=None,                                # ground lease; tenant-owned building
        bonus_dep_eligible=True,                            # new 2026 construction
        estimated_cost_seg_pct=None,
        extraction_confidence=0.55,
        needs_review=True,
        raw_data={
            "extraction_method": "manual_20260709",
            "hanley_listing_id": "EPg000009BJ8b",
            "broker_email_sender": "basher@hanleyinvestment.com",
            "broker_email_subject": "Just Listed: New Quick Quack Car Wash; Orange County, CA",
            "notes": "Ground lease — will STRUCTURAL_FAIL. Persisted to DB for record-keeping.",
            "brokers": ["Bill Asher <basher@hanleyinvestment.com> 949-585-7684",
                        "Jeff Lefko <jlefko@hanleyinvestment.com> 949-585-7682"],
        },
        first_seen=_NOW,
        last_seen=_NOW,
    ),

    # ── 3a. Valvoline — Wasco, CA ─────────────────────────────────────────────
    # Subject: "Just Listed: New Valvoline (20-Year Abs NNN Lease) & Grocery Outlet"
    # Quick-lube chain — not a car wash but passes NNN structural gates.
    Listing(
        source="hanley",
        source_listing_id="EPg000005exWL",
        channel="car_wash_nnn",
        listing_url="https://hanleyinvestmentgroup.com/listings/?id=EPg000005exWL",
        email_id="19f42b04ba6a71a7",
        title="Valvoline Instant Oil Change — Wasco, CA",
        address="Highway 46 Corridor, Wasco, CA",           # no street address in email
        city="Wasco",
        state="CA",
        zip="93280",
        price=3_000_000,
        cap_rate=None,                                      # not stated in email
        noi=None,
        sf=None,
        lot_acres=None,
        tenant="Valvoline",
        tenant_credit="public_corporate",                   # NYSE: VVV
        lease_type="absolute_nnn",                          # "20-year absolute NNN lease"
        lease_start=None,
        lease_expiration=None,
        term_remaining_years=20.0,
        escalator_pct=_ESC_10PCT_5YR,
        roof_structure="tenant",                            # absolute NNN implies no landlord resp.
        bonus_dep_eligible=True,                            # "brand-new construction"
        estimated_cost_seg_pct=None,
        extraction_confidence=0.50,
        needs_review=True,
        raw_data={
            "extraction_method": "manual_20260709",
            "hanley_listing_id": "EPg000005exWL",
            "combined_listing_id": "EPg000005ezRh",
            "broker_email_sender": "basher@hanleyinvestment.com",
            "broker_email_subject": "Just Listed: New Valvoline (20-Year Abs NNN Lease) & Grocery Outlet (12-Year Term); Central CA",
            "notes": "Quick-lube, not a car wash — routed to car_wash_nnn by Hanley domain mapping. No cap rate stated. New construction.",
            "brokers": ["Bill Asher <basher@hanleyinvestment.com> 949-585-7684"],
        },
        first_seen=_NOW,
        last_seen=_NOW,
    ),

    # ── 3b. Grocery Outlet — Wasco, CA ───────────────────────────────────────
    # Part of the combined Valvoline + Grocery Outlet email.
    # Lease type not described as NNN → will likely STRUCTURAL_FAIL.
    # Persisted to DB for record-keeping.
    Listing(
        source="hanley",
        source_listing_id="EPg0000005vqT",
        channel="car_wash_nnn",
        listing_url="https://hanleyinvestmentgroup.com/listings/?id=EPg0000005vqT",
        email_id="19f42b04ba6a71a7",
        title="Grocery Outlet — Wasco, CA",
        address="Highway 46 Corridor, Wasco, CA",
        city="Wasco",
        state="CA",
        zip="93280",
        price=5_470_000,
        cap_rate=None,
        noi=None,
        sf=None,
        lot_acres=None,
        tenant="Grocery Outlet",
        tenant_credit="public_corporate",                   # NASDAQ: GO
        lease_type=None,                                    # "15-year lease" — NNN structure not stated
        lease_start=None,
        lease_expiration=None,
        term_remaining_years=12.0,                          # "12 years remaining"
        escalator_pct=_ESC_10PCT_5YR,
        roof_structure=None,
        bonus_dep_eligible=None,
        estimated_cost_seg_pct=None,
        extraction_confidence=0.40,
        needs_review=True,
        raw_data={
            "extraction_method": "manual_20260709",
            "hanley_listing_id": "EPg0000005vqT",
            "combined_listing_id": "EPg000005ezRh",
            "broker_email_sender": "basher@hanleyinvestment.com",
            "broker_email_subject": "Just Listed: New Valvoline (20-Year Abs NNN Lease) & Grocery Outlet (12-Year Term); Central CA",
            "notes": "Grocery — not a car wash. Lease type not specified as NNN. Expect STRUCTURAL_FAIL.",
            "brokers": ["Bill Asher <basher@hanleyinvestment.com> 949-585-7684"],
        },
        first_seen=_NOW,
        last_seen=_NOW,
    ),
]


# ── Pipeline helpers replicated from pipeline.py ─────────────────────────────

def _top3(components: dict[str, float]) -> list[tuple[str, float]]:
    return sorted(components.items(), key=lambda kv: kv[1], reverse=True)[:3]


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    db.migrate()
    draft_out = Path("data/draft_request.json")
    draft_out.unlink(missing_ok=True)

    emails_processed = 3   # 3 Gmail threads, 4 listings (1 email had 2 listings)
    sources_active = ["hanley"]
    parser_failures: list[dict] = [
        {
            "parser": "hanley",
            "error": "no address found in body (Hanley blasts use city/state headers, not street addresses)",
            "msg": mid,
        }
        for mid in ["19f438bf9913eff5", "19f431b3b9c3e5f5", "19f42b04ba6a71a7"]
    ]

    new_count = 0
    updated_count = 0
    score_rows: list[DigestRow] = []

    for listing in LISTINGS:
        persisted_id, change = pipeline._persist_and_score(listing)
        if persisted_id is None:
            log.warning("persist_failed", title=listing.title)
            continue
        if change == "new":
            new_count += 1
        elif change == "updated":
            updated_count += 1

        # Score it.
        try:
            score = get_scorer(listing.channel).evaluate(listing)
        except Exception as e:
            log.warning("score_failed", channel=listing.channel, error=str(e))
            continue

        log.info(
            "listing_scored",
            title=listing.title,
            verdict=score.verdict,
            score=score.score,
            gates=score.structural_failures,
        )

        if score.verdict == "STRUCTURAL_FAIL":
            log.info("structural_fail_skipped", title=listing.title,
                     failures=score.structural_failures)
            continue

        score_rows.append(DigestRow(
            listing=listing,
            score=score.score,
            verdict=score.verdict,
            components_top3=_top3(score.components),
        ))

    score_rows.sort(key=lambda r: r.score, reverse=True)
    by_channel: dict[str, list[DigestRow]] = {}
    for r in score_rows:
        by_channel.setdefault(r.listing.channel, []).append(r)

    from app.digest import ScanStats
    digest = Digest(
        generated_at=utc_now(),
        overall_top10=score_rows[:10],
        by_channel=by_channel,
        price_drops=[],
        stats=ScanStats(
            emails_processed=emails_processed,
            listings_found=len(score_rows),
            listings_new=new_count,
            listings_updated=updated_count,
            sources_active=sources_active,
            sources_failed=[],
        ),
    )

    draft: DraftRequest | None = build_draft(digest)
    if draft is None:
        log.info("no_draft", reason="no qualifying listings")
        print("\nNo draft created (no qualifying listings after structural gates).")
        summary = {
            "started_at": digest.generated_at.isoformat(),
            "phase": "live_20260709",
            "emails_processed": emails_processed,
            "listings_found": 0,
            "listings_new": new_count,
            "listings_updated": updated_count,
            "parser_failures": parser_failures,
            "draft_created": False,
            "draft_id": None,
            "sources_active": sources_active,
            "sources_failed": [],
        }
    else:
        # Save draft for MCP caller to submit.
        draft_out.write_text(
            json.dumps({
                "to": draft.to,
                "subject": draft.subject,
                "html_body": draft.html_body,
                "text_body": draft.text_body,
            }, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        log.info("draft_saved", path=str(draft_out), subject=draft.subject)
        print(f"\n--- DRAFT SUBJECT ---\n{draft.subject}")
        summary = {
            "started_at": digest.generated_at.isoformat(),
            "phase": "live_20260709",
            "emails_processed": emails_processed,
            "listings_found": len(score_rows),
            "listings_new": new_count,
            "listings_updated": updated_count,
            "parser_failures": parser_failures,
            "draft_created": True,
            "draft_id": "pending-mcp-create",
            "sources_active": sources_active,
            "sources_failed": [],
        }

    # Append to run_log.json.
    log_path = Path("data/run_log.json")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    if log_path.exists():
        try:
            rows = json.loads(log_path.read_text())
        except Exception:
            rows = []
    rows.append(summary)
    rows = rows[-365:]
    log_path.write_text(json.dumps(rows, indent=2, default=str))

    print(json.dumps(
        {k: v for k, v in summary.items() if k != "parser_failures"},
        indent=2, default=str,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
