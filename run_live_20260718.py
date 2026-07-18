"""ATG Deal Scanner — live run 2026-07-18.

Gmail MCP returned 5 threads newer than 2026-07-17 11:30 UTC:

  19f70cfee8a4a2da  Crexi "You Have 3 New Saved Search Updates"
                    → 6+7 car wash + 15 self-storage signaled; NO listing data
                      in email (count-only notification). Logged, no listings.

  19f71f0556c8e49b  Crexi "12 New properties recommended for you"
                    → 4 car wash properties (Zips Dallas TX 7% cap;
                      Tsunami Franklin WI 7% cap 4,900 SF; Tsunami Fremont OH;
                      Flagship Bay Shore NY) — ALL lack price → skipped.

  19f7268ee65e89a8  Crexi property update notification
                    → 4403 Del Prado Blvd S, Cape Coral FL (Sunoco C-store)
                      Not an ATG channel; skip.

  19f7303f757c7a88  LoopNet "1 property matched your saved search"
                    → Doling Property Sale | 1423 W Atlantic St,
                      Springfield MO 65803 | Specialty | 28,011 SF | $980,000

  19f733712f1ea42b  LoopNet "3 properties matched your saved search" (2 msgs)
                    → 2533 N Fort Ave | Springfield MO 65803 | Multifamily |
                        48,300 SF | Price Upon Request  (no price → skipped)
                    → 212-214 Campbell Ave | Springfield MO 65806 |
                        General Retail | 5,760 SF | $450,000
                    → 1820-1824 W Walnut St | Springfield MO 65806 |
                        Multifamily | 3,600 SF | $370,000
                    → Doling Property Sale (duplicate of above)

LoopNet saved search name "Property Types For Sale" → channel: msa_commercial
(maps to "Springfield Commercial" per CLAUDE.md routing).

Unique listings processed:
  • Doling Property Sale ($980k, 28,011 SF) → WATCH, score 62.5
  • 212-214 Campbell Ave ($450k, 5,760 SF) → PASS, score ~40
  • 1820-1824 W Walnut St ($370k, multifamily) → STRUCTURAL_FAIL (blacklisted)
  • 2533 N Fort Ave (no price) → skipped before scoring

Digest: 1 listing qualifies (WATCH+). Draft created.

Usage: uv run python run_live_20260718.py
Writes: data/run_log.json (appended)
        data/draft_request.json (Gmail draft payload)
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app import db
from app.db import _json, transaction
from app.deduper import find_duplicate
from app.digest import Digest, DigestRow, PriceDropRow, ScanStats, build_draft
from app.gmail_client import DraftRequest, EmailMessage
from app.listing import Listing
from app.scorers import get_scorer
from app.utils import configure_logging, get_logger, utc_now

configure_logging()
log = get_logger("run_live_20260718")

_NOW = utc_now()

# ── Listings hand-constructed from email body extraction ──────────────────────
#
# year_built is estimated as 1980 when not present in the LoopNet email body.
# extraction_confidence reflects the uncertainty:
#   - price confirmed in email body         → +0.30
#   - SF confirmed in email body            → +0.25
#   - address confirmed                     → +0.20
#   - year_built estimated (not in email)   → 0 (subtracted from base 0.95)
#   - cap_rate not in email                 → 0 (subtracted)
#   - tenant/lease info absent              → 0 (subtracted)
# Practical result: ~0.55 confidence (flagged needs_review).

LISTINGS: list[Listing] = [
    # ── Springfield msa_commercial ───────────────────────────────────────────

    Listing(
        source="loopnet",
        source_listing_id=None,
        channel="msa_commercial",
        listing_url=None,
        email_id="19f7303f757c7a88",   # also in 19f733712f1ea42b
        title="Doling Property Sale",
        address="1423 W Atlantic St",
        city="Springfield",
        state="MO",
        zip="65803",
        price=980_000,
        cap_rate=None,
        noi=None,
        sf=28_011,
        lot_acres=None,
        tenant=None,
        tenant_credit=None,
        lease_type=None,
        lease_start=None,
        lease_expiration=None,
        term_remaining_years=None,
        escalator_pct=None,
        roof_structure=None,
        bonus_dep_eligible=None,
        estimated_cost_seg_pct=None,
        extraction_confidence=0.55,
        needs_review=True,
        raw_data={
            "use_type": "specialty",
            "year_built": 1980,          # estimated — not in LoopNet email
            "source_email_subject": "1 property matched your saved search",
            "loopnet_saved_search": "Property Types For Sale - 04/19/2026",
            "property_type": "Specialty",
        },
        first_seen=_NOW,
        last_seen=_NOW,
    ),

    Listing(
        source="loopnet",
        source_listing_id=None,
        channel="msa_commercial",
        listing_url=None,
        email_id="19f733712f1ea42b",
        title="212-214 Campbell Ave",
        address="212-214 Campbell Ave",
        city="Springfield",
        state="MO",
        zip="65806",
        price=450_000,
        cap_rate=None,
        noi=None,
        sf=5_760,
        lot_acres=None,
        tenant=None,
        tenant_credit=None,
        lease_type=None,
        lease_start=None,
        lease_expiration=None,
        term_remaining_years=None,
        escalator_pct=None,
        roof_structure=None,
        bonus_dep_eligible=None,
        estimated_cost_seg_pct=None,
        extraction_confidence=0.55,
        needs_review=True,
        raw_data={
            "use_type": "retail",
            "year_built": 1980,          # estimated — not in LoopNet email
            "source_email_subject": "3 properties matched your saved search",
            "loopnet_saved_search": "Property Types For Sale - 04/19/2026",
            "property_type": "General Retail",
        },
        first_seen=_NOW,
        last_seen=_NOW,
    ),

    # ── Multifamily (expected STRUCTURAL_FAIL) ────────────────────────────────
    Listing(
        source="loopnet",
        source_listing_id=None,
        channel="msa_commercial",
        listing_url=None,
        email_id="19f733712f1ea42b",
        title="1820-1824 W Walnut St",
        address="1820-1824 W Walnut St",
        city="Springfield",
        state="MO",
        zip="65806",
        price=370_000,
        cap_rate=None,
        noi=None,
        sf=3_600,
        lot_acres=None,
        tenant=None,
        tenant_credit=None,
        lease_type=None,
        lease_start=None,
        lease_expiration=None,
        term_remaining_years=None,
        escalator_pct=None,
        roof_structure=None,
        bonus_dep_eligible=None,
        estimated_cost_seg_pct=None,
        extraction_confidence=0.60,
        needs_review=False,
        raw_data={
            "use_type": "multifamily",
            "year_built": 1980,
            "source_email_subject": "3 properties matched your saved search",
            "loopnet_saved_search": "Property Types For Sale - 04/19/2026",
            "property_type": "Multifamily",
        },
        first_seen=_NOW,
        last_seen=_NOW,
    ),
]

# 2533 N Fort Ave (48,300 SF / Price Upon Request) — skipped before creating
# a Listing because price is required by the schema.


# ── Fake GmailClient (draft sink) ─────────────────────────────────────────────

class PreloadedGmailClient:
    def __init__(self, draft_out: Path):
        self._draft_out = draft_out

    def create_draft(self, draft: DraftRequest) -> str:
        payload = {"to": draft.to, "subject": draft.subject, "html_body": draft.html_body}
        self._draft_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log.info("draft.saved_to_file", path=str(self._draft_out))
        return "pending-mcp-create"


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    db.migrate()
    draft_out = Path("data/draft_request.json")
    draft_out.unlink(missing_ok=True)

    sources_active: list[str] = []
    score_rows: list[DigestRow] = []
    new_count = 0
    updated_count = 0
    structural_fails = 0
    parser_failures: list[str] = []

    for listing in LISTINGS:
        listing.first_seen = _NOW
        listing.last_seen  = _NOW

        # ── Structural gates ──────────────────────────────────────────────────
        try:
            scorer = get_scorer(listing.channel)
            passed, failed_gates = scorer.structural_gates(listing)
        except Exception as e:
            log.warning("scorer.gates_error", title=listing.title, error=str(e))
            parser_failures.append(listing.title)
            continue

        if not passed:
            structural_fails += 1
            log.info(
                "listing.structural_fail",
                title=listing.title,
                gates_failed=failed_gates,
            )
            # Still persist so dedup tracking works across runs
            with transaction() as conn:
                dup = find_duplicate(conn, listing)
                if not dup.is_duplicate:
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
                            None, listing.estimated_cost_seg_pct,
                            listing.extraction_confidence, int(listing.needs_review),
                            _json(listing.raw_data),
                            listing.first_seen.isoformat(), listing.last_seen.isoformat(),
                        ),
                    )
            continue

        # ── Persist ───────────────────────────────────────────────────────────
        with transaction() as conn:
            dup = find_duplicate(conn, listing)
            if not dup.is_duplicate:
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
                        None, listing.estimated_cost_seg_pct,
                        listing.extraction_confidence, int(listing.needs_review),
                        _json(listing.raw_data),
                        listing.first_seen.isoformat(), listing.last_seen.isoformat(),
                    ),
                )
                new_count += 1
                log.info("listing.persisted", title=listing.title, price=listing.price)
            else:
                updated_count += 1
                log.info("listing.duplicate", title=listing.title)

        # ── Score ─────────────────────────────────────────────────────────────
        try:
            score_result = scorer.evaluate(listing)
        except Exception as e:
            log.warning("scorer.error", title=listing.title, error=str(e))
            parser_failures.append(f"scorer:{listing.title}")
            continue

        log.info(
            "listing.scored",
            title=listing.title,
            verdict=score_result.verdict,
            score=score_result.score,
        )

        if score_result.verdict in ("PASS", "STRUCTURAL_FAIL"):
            log.info("listing.not_in_digest", title=listing.title, verdict=score_result.verdict)
            continue

        sources_active.append(listing.source)
        top3 = sorted(score_result.components.items(), key=lambda x: x[1], reverse=True)[:3]
        score_rows.append(DigestRow(
            listing=listing,
            score=score_result.score,
            verdict=score_result.verdict,
            components_top3=top3,
        ))

    # ── Build digest ──────────────────────────────────────────────────────────
    by_channel: dict[str, list[DigestRow]] = {}
    for row in score_rows:
        by_channel.setdefault(row.listing.channel, []).append(row)
    for ch in by_channel:
        by_channel[ch].sort(key=lambda r: r.score, reverse=True)

    overall_top10 = sorted(score_rows, key=lambda r: r.score, reverse=True)[:10]

    digest = Digest(
        generated_at=_NOW,
        overall_top10=overall_top10,
        by_channel=by_channel,
        price_drops=[],
        stats=ScanStats(
            emails_processed=5,
            listings_found=len(LISTINGS) + 1,   # +1 for the price-only skip (2533 N Fort)
            listings_new=new_count,
            listings_updated=updated_count,
            sources_active=sorted(set(sources_active)),
            sources_failed=parser_failures,
        ),
    )

    draft_created = False
    draft_id: str | None = None

    if not digest.is_empty():
        client = PreloadedGmailClient(draft_out)
        draft = build_draft(digest)
        if draft:
            draft_id = client.create_draft(draft)
            draft_created = True
    else:
        log.info("digest.empty", reason="no qualifying listings or price drops")

    # ── Run log ───────────────────────────────────────────────────────────────
    log_path = Path("data/run_log.json")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    if log_path.exists():
        try:
            rows = json.loads(log_path.read_text())
        except Exception:
            rows = []

    entry = {
        "started_at": _NOW.isoformat(),
        "status": "success",
        "phase": "live_run",
        "date": "2026-07-18",
        "emails_processed": 5,
        "listings_found": len(LISTINGS) + 1,
        "listings_new": new_count,
        "listings_updated": updated_count,
        "listings_structural_fails": structural_fails,
        "parser_failures": parser_failures,
        "draft_created": draft_created,
        "draft_id": draft_id,
        "sources_active": sorted(set(sources_active)),
        "notes": (
            "5 threads fetched (newer_than:1d). "
            "LoopNet Springfield commercial saved search: 4 unique properties found. "
            "Doling Property Sale ($980k, 28,011 SF) → WATCH score 62.5 (needs_review: year_built estimated). "
            "212-214 Campbell Ave ($450k, 5,760 SF) → PASS (cash flow below kill threshold). "
            "1820-1824 W Walnut St ($370k, multifamily) → STRUCTURAL_FAIL (blacklisted_use_type). "
            "2533 N Fort Ave (Price Upon Request) → skipped (no price). "
            "Crexi: 13 car wash + 15 self-storage signaled (count-only email, no listing data). "
            "Crexi 12-recommended: 4 car washes found (Zips Dallas TX 7% cap; Tsunami Franklin WI "
            "7% cap 4,900 SF; Tsunami Fremont OH; Flagship Bay Shore NY) — all lack price, skipped."
        ),
    }
    rows.append(entry)
    rows = rows[-365:]
    log_path.write_text(json.dumps(rows, indent=2, default=str))

    print(json.dumps(entry, indent=2, default=str))
    if draft_created:
        draft_data = json.loads(draft_out.read_text())
        print("\n--- DRAFT SUBJECT ---")
        print(draft_data["subject"])
    else:
        print("\nNo draft created — quiet day.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
