"""ATG Deal Scanner — live run 2026-08-07.

Gmail MCP returned 2 threads newer_than:1d from broker domains:

  19fd80ec4b8e319c  Sands IG "Meet the Operator Behind Willowbrae Academy"
                    (info@sandsig.com) — brand/content email profiling a
                    Willowbrae Academy childcare franchisee. No price, cap rate,
                    or standard SIG listing format. Parser yields no listing.

  19fd7a72f1d08eb5  Sands IG "Just Listed | 6-Bay Automotive Facility -
                    Signalized Corner | $800K | Sale or Lease | Buffalo, NY"
                    (luke@sandsig.com) — 3,678 SF automotive redevelopment at
                    315 Niagara Street, Buffalo, NY. $800K, owner-user or
                    redevelopment play. No NNN lease, no tenant in place.

Source routing: both *@sandsig.com → (car_wash_nnn, ios) / sands_ig parser.

Email 1 analysis:
  - No "at <address> in <city>, <state>" SIG pattern in body
  - No PRICE block found
  - Parser returns no listing (no price → skip)

Email 2 analysis:
  - Address: 315 Niagara Street, Buffalo, NY ✓
  - Price: $800,000 ✓
  - SF: 3,678 SF ✓
  - Cap rate: None
  - Lease: "Owner-User Automotive or Redevelopment" — no NNN structure
  - Both "for sale" and "for lease" present → parser doesn't skip
  - Channel: car_wash_nnn (no ios/outdoor/yard in subject)
  - Structural gates for car_wash_nnn: ALL FAIL
      - lease_type=None (not absolute_nnn)
      - bonus_dep_eligible=None (not True)
      - roof_structure=None (not tenant)
  - IOS filter: $800K < $2M minimum → also fails

Result: 0 qualifying listings. Quiet day — no draft created.

Usage: uv run python run_live_20260807.py
Writes: data/run_log.json (appended)
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app import db
from app.deduper import find_duplicate
from app.db import _json, transaction
from app.digest import Digest, DigestRow, PriceDropRow, ScanStats, build_draft
from app.gmail_client import EmailMessage
from app.listing import Listing
from app.parsers.sands_ig import SandsIgParser
from app.scorers import get_scorer
from app.utils import configure_logging, get_logger, utc_now

configure_logging()
log = get_logger("run_live_20260807")

_NOW = utc_now()

# ── Raw emails fetched from Gmail MCP (2026-08-07 06:30 CT) ──────────────────

RAW_EMAILS = [
    EmailMessage(
        id="19fd80ec4b8e319c",
        thread_id="19fd80ec4b8e319c",
        sender="info@sandsig.com",
        subject="Meet the Operator Behind Willowbrae Academy",
        received_at="2026-08-06T17:03:28Z",
        text_body=(
            "Learn more about an early education operator.\n\n"
            "MEET AN EARLY EDUCATION OPERATOR\n\n"
            "HARP KHELA\nFranchise Owner and Operator\n\n"
            "Since 2009, Willowbrae Childcare Academy has offered programs to families for "
            "infants to school age children.\n\n"
            "Interested in Investing in a Willowbrae Academy?\n"
            "Explore our exclusive SIG listing below.\n\n"
            "Willowbrae Academy  |  Georgetown, TX\n\n"
            "SIG - Sands Investment Group - SC, 238 Mathis Ferry Road, Suite 102, "
            "Mount Pleasant, South Carolina 29464, United States\n"
        ),
    ),
    EmailMessage(
        id="19fd7a72f1d08eb5",
        thread_id="19fd7a72f1d08eb5",
        sender="luke@sandsig.com",
        subject="Just Listed | 6-Bay Automotive Facility - Signalized Corner | $800K | Sale or Lease | Buffalo, NY",
        received_at="2026-08-06T15:03:41Z",
        text_body=(
            "Sands Investment Group is pleased to exclusively offer for sale or for lease the 3,678 SF "
            "Automotive Redevelopment Asset located at 315 Niagara Street in Buffalo, NY.\n\n"
            "Automotive Redevelopment - Buffalo, NY\n\n"
            "PRICE\n\n$800,000\n\n"
            "SQUARE FOOTAGE\n\n3,678 SF\n\n"
            "Investment Highlights\n\n"
            "Available for sale and for lease: Contact the broker for the lease rates\n"
            "Owner-User or Redevelopment Opportunity: Owner-User Automotive or Redevelopment opportunity "
            "with 3,678 SF and 6 service bays on a 0.31-acre parcel.\n"
            "Strong Local Frontage: The property features prominent frontage along Empire Street Trail "
            "(16,162 VPD) and is located less than a mile from Downtown Buffalo and City Hall.\n"
            "Excellent Interstate Access & Traffic Counts: Located off Exit 8 of I-190 (81,123 VPD) "
            "and over 16,000 VPD in front of the site.\n"
            "Signalized Corner Offered Below Replacement Cost: Excellent opportunity at a signalized "
            "intersection offered significantly below replacement cost.\n\n"
            "Investment Advisors\n\nLuke Wakefield\nGA Lic. # 361563\n770.800.3035\nluke@SandsIG.com\n\n"
            "Munir Meghjani\nGA Lic. # 366616\n770.501.3007\nmunir@SandsIG.com\n"
        ),
    ),
]


def main() -> int:
    db.migrate()
    parser = SandsIgParser()

    parse_results = []
    parser_failures = []
    sources_active = set()

    for msg in RAW_EMAILS:
        log.info("processing_email", id=msg.id, subject=msg.subject, sender=msg.sender)
        try:
            result = parser.parse(msg)
            parse_results.append((msg, result))
            sources_active.add("sands_ig")
            for w in result.warnings:
                log.debug("parser.warning", warning=w)
        except Exception as e:
            log.error("parser.exception", id=msg.id, error=str(e))
            parser_failures.append({"parser": "sands_ig", "error": str(e), "msg": msg.id})

    structural_fails: list[tuple[str, list[str]]] = []
    score_rows: list[DigestRow] = []
    new_count = 0
    listings_found = 0

    for msg, result in parse_results:
        for listing in result.listings:
            listings_found += 1
            scorer = get_scorer(listing.channel)
            gates_ok, gates_failed = scorer.structural_gates(listing)

            if not gates_ok:
                log.info(
                    "pipeline.structural_fail",
                    title=listing.title,
                    channel=listing.channel,
                    gates=gates_failed,
                    price=listing.price,
                    state=listing.state,
                )
                structural_fails.append((listing.title, gates_failed))
                # Persist to DB for record-keeping.
                with transaction() as conn:
                    dup = find_duplicate(conn, listing)
                    if not dup.is_duplicate:
                        listing.first_seen = _NOW
                        listing.last_seen = _NOW
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

            try:
                score = scorer.evaluate(listing)
            except Exception as e:
                log.warning("pipeline.score_failed", channel=listing.channel, error=str(e))
                continue
            if score.verdict != "STRUCTURAL_FAIL":
                score_rows.append(DigestRow(
                    listing=listing, score=score.score, verdict=score.verdict,
                    components_top3=sorted(
                        score.components.items(), key=lambda kv: kv[1], reverse=True
                    )[:3],
                ))

    # ── Digest ────────────────────────────────────────────────────────────────
    digest = Digest(
        generated_at=_NOW,
        overall_top10=score_rows[:10],
        by_channel={},
        price_drops=[],
        stats=ScanStats(
            emails_processed=len(RAW_EMAILS),
            listings_found=listings_found,
            listings_new=new_count,
            listings_updated=0,
            sources_active=sorted(sources_active),
            sources_failed=[f["parser"] for f in parser_failures],
        ),
    )

    # Quiet day: 0 qualifying listings → skip draft.
    log.info(
        "run.quiet_day",
        emails=len(RAW_EMAILS),
        listings_found=listings_found,
        structural_fails=len(structural_fails),
        qualifying=len(score_rows),
        note=(
            "2 SandsIG emails today. "
            "Email 1: brand/content profile of Willowbrae Academy franchisee — no listing data. "
            "Email 2: 6-Bay Automotive Facility Buffalo NY $800K — STRUCTURAL_FAIL "
            "(no NNN lease, no bonus dep eligible, no roof=tenant; also $800K below ios $2M min). "
            "No qualifying listings. No draft created."
        ),
    )

    summary = {
        "started_at": _NOW.isoformat(),
        "phase": "live_run",
        "date": "2026-08-07",
        "emails_processed": len(RAW_EMAILS),
        "listings_found": listings_found,
        "listings_new": new_count,
        "listings_updated": 0,
        "structural_fails": [{"title": t, "gates": g} for t, g in structural_fails],
        "qualifying_listings": len(score_rows),
        "parser_failures": parser_failures,
        "draft_created": False,
        "draft_id": None,
        "sources_active": sorted(sources_active),
        "sources_failed": sorted({f["parser"] for f in parser_failures}),
        "notes": (
            "2 SandsIG emails: "
            "(1) 'Meet the Operator Behind Willowbrae Academy' — content/brand email, no listing data. "
            "(2) 'Just Listed | 6-Bay Automotive Facility | $800K | Buffalo, NY' — "
            "automotive redevelopment, owner-user, no NNN lease. "
            "STRUCTURAL_FAIL on car_wash_nnn (lease_type=None, bonus_dep_eligible=None, "
            "roof_structure=None). $800K also below ios $2M minimum. Quiet day."
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

    print(json.dumps(summary, indent=2, default=str))
    print("\nQuiet day — 0 qualifying listings. No draft created.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
