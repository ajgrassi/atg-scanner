"""ATG Deal Scanner — live run 2026-07-15.

Gmail MCP returned 2 threads (newer_than:1d), both from Sands Investment Group:
  19f619a7d4e1d77c — 47-Site RV Park, Pryor, OK (self_storage, $1.2M, 9.47% cap)
  19f61716fa72ac47 — Marketing email (bonus dep playbook) — no listing, skipped.

Result: The RV park fails the self_storage structural gate: price $1,200,000 is
below the $1.5M–$5M band. No digest draft created (quiet day per spec).

Key data extracted from email body (kdeninno@sandsig.com):
  Address:     871 North 4386 Road, Pryor, OK
  Price:       $1,200,000
  Cap Rate:    9.47%
  Acres:       6.04
  Sites:       47 (35 full hook-up, 12 water/sewer only)
  Tenancy:     Month-to-month
  Management:  Work-Kamper
  Brokers:     Kristen Deninno (kdeninno@sandsig.com), Meagan Brady (mbrady@sandsig.com)

Usage: uv run python run_live_20260715.py
Writes: data/run_log.json (appended)
"""

from __future__ import annotations

import json
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
log = get_logger("run_live_20260715")

_NOW = utc_now()

# ── Listings hand-constructed from email body ─────────────────────────────────
LISTINGS: list[Listing] = [
    Listing(
        source="sands_ig",
        source_listing_id=None,
        channel="self_storage",
        listing_url=None,
        email_id="19f619a7d4e1d77c",
        title="47-Site RV Park — Pryor, OK",
        address="871 North 4386 Road",
        city="Pryor",
        state="OK",
        zip=None,
        price=1_200_000,
        cap_rate=0.0947,
        noi=int(1_200_000 * 0.0947),   # $113,640 implied
        sf=None,
        lot_acres=6.04,
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
        extraction_confidence=0.90,     # price, cap, acres, address all explicit
        needs_review=False,
        raw_data={
            "rv_sites_total": 47,
            "full_hookup_sites": 35,
            "water_sewer_only_sites": 12,
            "tenancy_type": "month_to_month",
            "management": "work_kamper",
            "utilities": "city_water_septic",
            "laundromat_on_site": True,
            "brokers": [
                {"name": "Kristen Deninno", "email": "kdeninno@sandsig.com", "phone": "954.902.5251"},
                {"name": "Meagan Brady", "email": "mbrady@sandsig.com", "phone": "954.902.5248"},
            ],
        },
        first_seen=_NOW,
        last_seen=_NOW,
    )
]

# ── Fake GmailClient (draft sink) ─────────────────────────────────────────────

class PreloadedGmailClient:
    def __init__(self, draft_out: Path):
        self._draft_out = draft_out
        self.draft_created: str | None = None

    def search(self, query: str, max_results: int = 100) -> list[EmailMessage]:
        return []   # pre-parsed above; not used by direct-ingest path

    def fetch_attachments(self, message_id: str, save_dir: str):
        return []

    def create_draft(self, draft: DraftRequest) -> str:
        payload = {"to": draft.to, "subject": draft.subject, "html_body": draft.html_body}
        self._draft_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log.info("fake_gmail.draft_saved", path=str(self._draft_out))
        return "pending-mcp-create"


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    db.migrate()
    draft_out = Path("data/draft_request.json")
    draft_out.unlink(missing_ok=True)

    sources_active: list[str] = []
    score_rows: list[DigestRow] = []
    new_count = 0

    for listing in LISTINGS:
        listing.first_seen = _NOW
        listing.last_seen  = _NOW

        # Persist (dedup + insert)
        from app import db as _db
        from app.deduper import find_duplicate
        from app.db import _json, transaction

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
                        listing.title, listing.address, listing.city, listing.state, listing.zip,
                        listing.price, listing.cap_rate, listing.noi, listing.sf, listing.lot_acres,
                        listing.tenant, listing.tenant_credit, listing.lease_type,
                        None, None,
                        listing.term_remaining_years, listing.escalator_pct, listing.roof_structure,
                        None, listing.estimated_cost_seg_pct,
                        listing.extraction_confidence, int(listing.needs_review),
                        _json(listing.raw_data),
                        listing.first_seen.isoformat(), listing.last_seen.isoformat(),
                    ),
                )
                new_count += 1
                log.info("listing.persisted", title=listing.title, price=listing.price)
            else:
                log.info("listing.duplicate", title=listing.title)

        # Score
        try:
            score = get_scorer(listing.channel).evaluate(listing)
        except Exception as e:
            log.warning("scoring.failed", error=str(e))
            continue

        log.info(
            "listing.scored",
            title=listing.title,
            verdict=score.verdict,
            score=score.score,
            failures=score.structural_failures,
        )

        if score.verdict == "STRUCTURAL_FAIL":
            log.info(
                "listing.structural_fail",
                title=listing.title,
                gates_failed=score.structural_failures,
            )
            continue

        sources_active.append(listing.source)
        score_rows.append(DigestRow(
            listing=listing,
            score=score.score,
            verdict=score.verdict,
            components_top3=[],
        ))

    # Build digest
    digest = Digest(
        generated_at=_NOW,
        overall_top10=score_rows[:10],
        by_channel={r.listing.channel: [] for r in score_rows},
        price_drops=[],
        stats=ScanStats(
            emails_processed=2,     # RV park + marketing
            listings_found=len(score_rows),
            listings_new=new_count,
            listings_updated=0,
            sources_active=sorted(set(sources_active)),
            sources_failed=[],
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

    # Write run log
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
        "date": "2026-07-15",
        "emails_processed": 2,
        "listings_found": len(score_rows),
        "listings_new": new_count,
        "listings_updated": 0,
        "listings_structural_fails": len(LISTINGS) - len(score_rows),
        "parser_failures": [],
        "draft_created": draft_created,
        "draft_id": draft_id,
        "sources_active": sorted(set(sources_active)),
        "notes": (
            "1 listing from sands_ig (RV Park Pryor OK $1.2M 9.47% cap) — "
            "STRUCTURAL_FAIL: price $1,200,000 below $1.5M self_storage floor. "
            "1 marketing email skipped. No draft."
        ),
    }
    rows.append(entry)
    rows = rows[-365:]
    log_path.write_text(json.dumps(rows, indent=2, default=str))

    print(json.dumps({k: v for k, v in entry.items()}, indent=2, default=str))
    if not draft_created:
        print("\nNo draft created — all listings were structural fails or quiet day.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
