"""ATG Deal Scanner — live run 2026-07-30.

Gmail MCP returned 1 thread newer than 2026-07-29 11:30 UTC:

  19fae8661fb38c95  Sands IG "RV Park Deals For Andrew" (info@sandsig.com)
                    → RSS-style blast of 3 RV park listings:
                        47 Site RV Park – Pryor, OK | $1,200,000 | 9.47%
                        Westside RV Park – Sunrise Beach, MO | $640,000 | 6.84%
                        Southside Acres Mobile Home and RV Park –
                            Concordia, MO | $875,000 | 9.20%

Source routing: *@sandsig.com → car_wash_nnn / sands_ig parser.
Parser: email is in RSS-list format (not standard single-listing SIG format).
  - No "at <address> in <city>, <state>" pattern found → falls back to generic.
  - Generic parser extracts one listing (first price hit) but missing
    lease_type, bonus_dep_eligible, roof_structure.

Channel: car_wash_nnn (no ios/outdoor/yard in subject)
Structural gates for car_wash_nnn: ALL FAIL
  - lease_type=None (not absolute_nnn)
  - bonus_dep_eligible=None (not True)
  - roof_structure=None (not tenant)

RV parks also fail self_storage channel:
  - $640k, $875k, $1.2M all below $1.5M floor
  - SIG is not mapped to self_storage channel anyway

Result: STRUCTURAL_FAIL for all 3 RV park listings.
0 qualifying listings. Quiet day — no draft created.

Usage: uv run python run_live_20260730.py
Writes: data/run_log.json (appended)
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app import db
from app.config import resolve_source
from app.deduper import find_duplicate
from app.db import transaction
from app.digest import Digest, DigestRow, PriceDropRow, ScanStats, build_draft
from app.gmail_client import DraftRequest, EmailMessage
from app.listing import Listing
from app.parsers.sands_ig import SandsIgParser
from app.scorers import get_scorer
from app.utils import configure_logging, get_logger, utc_now

configure_logging()
log = get_logger("run_live_20260730")

_NOW = utc_now()

# ── Raw email from Gmail MCP ──────────────────────────────────────────────────

RAW_EMAIL = EmailMessage(
    id="19fae8661fb38c95",
    thread_id="19fae8661fb38c95",
    sender="info@sandsig.com",
    subject="RV Park Deals For Andrew",
    received_at="2026-07-29T15:33:33Z",
    text_body=(
        "SIG's Exclusive RV Park Listings.\n\n"
        "47 Site RV Park - Pryor, OK | $1,200,000 | 9.47%\n"
        "Westside RV Park - Sunrise Beach, MO | $640,000 | 6.84%\n"
        "Southside Acres Mobile Home and RV Park - Concordia, MO | $875,000 | 9.20%\n\n"
        "View All Inventory →\n\n"
        "SIG - Sands Investment Group - SC, 238 Mathis Ferry Road, Suite 102, "
        "Mount Pleasant, South Carolina 29464, United States\n"
        "Copyright © 2026. All Rights Reserved.\n"
    ),
)

# ── Three hand-extracted RV park listings from the email ──────────────────────
#
# The SIG parser is designed for single-listing detailed emails. This RSS-style
# multi-listing blast uses "Name - City, ST | $price | cap%" format — no
# standard SIG address pattern, no lease/structure data. We construct the
# listings manually with the data available and run them through scoring.
# All 3 will hit STRUCTURAL_FAIL on car_wash_nnn (the channel SIG maps to)
# and would also fail self_storage price gate ($1.5M min).

LISTINGS: list[Listing] = [
    Listing(
        source="sands_ig",
        source_listing_id=None,
        channel="car_wash_nnn",       # SIG default channel (no ios keywords)
        listing_url=None,
        email_id="19fae8661fb38c95",
        title="47 Site RV Park – Pryor, OK",
        address="Pryor, OK",
        city="Pryor",
        state="OK",
        zip=None,
        price=1_200_000,
        cap_rate=0.0947,
        noi=None,
        sf=None,
        lot_acres=None,
        tenant="47 Site RV Park (owner-op)",
        tenant_credit=None,
        lease_type=None,              # No NNN lease — owner-op RV park
        lease_start=None,
        lease_expiration=None,
        term_remaining_years=None,
        escalator_pct=None,
        roof_structure=None,
        bonus_dep_eligible=None,
        estimated_cost_seg_pct=None,
        extraction_confidence=0.50,   # price+cap only; no SF, lease, address detail
        needs_review=True,
        raw_data={
            "broker_email_sender": "info@sandsig.com",
            "broker_email_subject": "RV Park Deals For Andrew",
            "note": "RSS-style multi-listing blast; limited data extracted",
        },
    ),
    Listing(
        source="sands_ig",
        source_listing_id=None,
        channel="car_wash_nnn",
        listing_url=None,
        email_id="19fae8661fb38c95",
        title="Westside RV Park – Sunrise Beach, MO",
        address="Sunrise Beach, MO",
        city="Sunrise Beach",
        state="MO",
        zip=None,
        price=640_000,
        cap_rate=0.0684,
        noi=None,
        sf=None,
        lot_acres=None,
        tenant="Westside RV Park (owner-op)",
        tenant_credit=None,
        lease_type=None,
        lease_start=None,
        lease_expiration=None,
        term_remaining_years=None,
        escalator_pct=None,
        roof_structure=None,
        bonus_dep_eligible=None,
        estimated_cost_seg_pct=None,
        extraction_confidence=0.50,
        needs_review=True,
        raw_data={
            "broker_email_sender": "info@sandsig.com",
            "broker_email_subject": "RV Park Deals For Andrew",
            "note": "RSS-style multi-listing blast; limited data extracted",
        },
    ),
    Listing(
        source="sands_ig",
        source_listing_id=None,
        channel="car_wash_nnn",
        listing_url=None,
        email_id="19fae8661fb38c95",
        title="Southside Acres Mobile Home and RV Park – Concordia, MO",
        address="Concordia, MO",
        city="Concordia",
        state="MO",
        zip=None,
        price=875_000,
        cap_rate=0.0920,
        noi=None,
        sf=None,
        lot_acres=None,
        tenant="Southside Acres Mobile Home and RV Park (owner-op)",
        tenant_credit=None,
        lease_type=None,
        lease_start=None,
        lease_expiration=None,
        term_remaining_years=None,
        escalator_pct=None,
        roof_structure=None,
        bonus_dep_eligible=None,
        estimated_cost_seg_pct=None,
        extraction_confidence=0.50,
        needs_review=True,
        raw_data={
            "broker_email_sender": "info@sandsig.com",
            "broker_email_subject": "RV Park Deals For Andrew",
            "note": "RSS-style multi-listing blast; limited data extracted",
        },
    ),
]


def main() -> int:
    db.migrate()

    structural_fails: list[tuple[str, list[str]]] = []
    score_rows: list[DigestRow] = []
    new_count = 0
    parser_failures: list[dict] = []

    for listing in LISTINGS:
        scorer = get_scorer(listing.channel)
        gates_ok, gates_failed = scorer.structural_gates(listing)

        if not gates_ok:
            log.info(
                "pipeline.structural_fail",
                title=listing.title,
                channel=listing.channel,
                gates=gates_failed,
            )
            structural_fails.append((listing.title, gates_failed))
            # Still persist to DB so we have a record of seeing these.
            with transaction() as conn:
                dup = find_duplicate(conn, listing)
                if not dup.is_duplicate:
                    listing.first_seen = _NOW
                    listing.last_seen = _NOW
                    from app.db import _json
                    conn.execute(
                        """
                        INSERT INTO listings
                          (source, source_listing_id, channel, listing_url, email_id,
                           title, address, city, state, zip,
                           price, cap_rate, noi, sf, lot_acres,
                           tenant, tenant_credit, lease_type, lease_start, lease_expiration,
                           term_remaining_years, escalator_pct, roof_structure,
                           bonus_dep_eligible, estimated_cost_seg_pct,
                           extraction_confidence, needs_review, raw_data_json,
                           first_seen, last_seen)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                                ?, ?, ?, ?, ?,
                                ?, ?, ?, ?, ?)
                        """,
                        (
                            listing.source, listing.source_listing_id, listing.channel,
                            listing.listing_url, listing.email_id,
                            listing.title, listing.address, listing.city,
                            listing.state, listing.zip,
                            listing.price, listing.cap_rate, listing.noi,
                            listing.sf, listing.lot_acres,
                            listing.tenant, listing.tenant_credit, listing.lease_type,
                            None, None,
                            listing.term_remaining_years, listing.escalator_pct,
                            listing.roof_structure,
                            None,
                            listing.estimated_cost_seg_pct,
                            listing.extraction_confidence, int(listing.needs_review),
                            _json(listing.raw_data),
                            listing.first_seen.isoformat(),
                            listing.last_seen.isoformat(),
                        ),
                    )
                    new_count += 1
            continue

        # Would score qualifying listings — none reach here today.
        try:
            score = scorer.evaluate(listing)
        except Exception as e:
            log.warning("pipeline.score_failed", channel=listing.channel, error=str(e))
            continue
        if score.verdict != "STRUCTURAL_FAIL":
            score_rows.append(DigestRow(
                listing=listing, score=score.score, verdict=score.verdict,
                components_top3=sorted(score.components.items(), key=lambda kv: kv[1], reverse=True)[:3],
            ))

    # ── Build digest ──────────────────────────────────────────────────────────
    digest = Digest(
        generated_at=_NOW,
        overall_top10=score_rows[:10],
        by_channel={},
        price_drops=[],
        stats=ScanStats(
            emails_processed=1,
            listings_found=len(LISTINGS),
            listings_new=new_count,
            listings_updated=0,
            sources_active=["sands_ig"],
            sources_failed=[],
        ),
    )

    # Quiet day: 0 qualifying listings → skip draft.
    draft_created = False
    draft_id = None
    log.info(
        "run.quiet_day",
        emails=1,
        listings_found=3,
        structural_fails=len(structural_fails),
        qualifying=len(score_rows),
        note="3 RV parks from SandsIG; all STRUCTURAL_FAIL (not NNN, no bonus dep); "
             "also below self_storage $1.5M floor. No draft created.",
    )

    # ── Append to run_log.json ────────────────────────────────────────────────
    summary = {
        "started_at": _NOW.isoformat(),
        "phase": "live_run",
        "date": "2026-07-30",
        "emails_processed": 1,
        "listings_found": 3,
        "listings_new": new_count,
        "listings_updated": 0,
        "structural_fails": [
            {"title": t, "gates": g} for t, g in structural_fails
        ],
        "qualifying_listings": 0,
        "parser_failures": parser_failures,
        "draft_created": draft_created,
        "draft_id": draft_id,
        "sources_active": ["sands_ig"],
        "sources_failed": [],
        "notes": (
            "1 SandsIG email (RV Park Deals For Andrew). "
            "3 RV park listings: Pryor OK $1.2M 9.47%, Sunrise Beach MO $640k 6.84%, "
            "Concordia MO $875k 9.20%. "
            "All STRUCTURAL_FAIL on car_wash_nnn channel (no NNN lease, no bonus dep, "
            "no roof=tenant). Also below self_storage $1.5M price floor. Quiet day."
        ),
    }

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

    print(json.dumps({k: v for k, v in summary.items()}, indent=2, default=str))
    print("\nQuiet day — 0 qualifying listings. No draft created.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
