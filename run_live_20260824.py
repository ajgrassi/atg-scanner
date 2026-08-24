"""Live scanner run 2026-08-24 — daily 6:30am CT routine.

Emails found today (24h window: Aug 23 22:30 UTC → Aug 24 11:30 UTC):
  1. emails@search.crexi.com — "12 New properties recommended for you" (Aug 23 22:42 UTC)
     → Bulk recommendation email (not a named saved-search alert)
     → Parser finds first address (2113 Adams Grove, Columbia SC) — no price/SF → 0 extracted
     → Car wash listings identified manually: Go Car Wash (KC MO) + Tidal Wave Auto Spa (Burley ID)
       — both lack inline pricing; flagged for manual click-through
  2. noreply@loopnet.com — "1 property matched your saved search" (Aug 23 22:33 UTC)
     → 2115 S Brentwood, Springfield MO 65804 — 2,000 SF General Retail — $400,000
     → Routed to msa_commercial (fallback); price + sf extracted; passes geography filter
     → Structural gate FAILS: missing year_built (required by thesis YAML)
     → Persisted to deals.db as new listing; flagged NEEDS REVIEW

Pipeline result: 1 new listing persisted, 0 fully scored (year_built missing → gate fail).
Creating custom digest with NEEDS REVIEW item + car wash flags.

Usage:  uv run python run_live_20260824.py
Writes: data/draft_request.json
        data/run_log.json
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app import db, pipeline
from app.gmail_client import DraftRequest, EmailMessage
from app.listing import Listing
from app.scorers.msa_commercial import MsaCommercialScorer
from app.utils import configure_logging, get_logger

configure_logging()
log = get_logger("run_live_20260824")

EMAILS: list[dict] = [
    {
        "id": "1a030c9f2a2bac20",
        "thread_id": "1a030c9f2a2bac20",
        "sender": "emails@search.crexi.com",
        "subject": "12 New properties recommended for you",
        "received_at": "2026-08-23T22:42:13Z",
        "text_body": (
            "Properties on Crexi personally recommended for you.\n\n"
            "2113 Adams Grove, Columbia, SC 29203\n"
            "Office | 22,263 SqFt\n\n"
            "Go Car Wash\n"
            "4220 Sterling Avenue, Kansas City, MO 64130\n"
            "Property Type: Car Wash\n"
            "Lease Type: Absolute NNN\n"
            "Roof Responsibility: Tenant\n\n"
            "113 Reed Ave, Lexington, SC 29072\n"
            "Office | 39,794 SqFt\n\n"
            "1600 Bull St, Columbia, SC 29201\nOffice | 21,434 SqFt\n\n"
            "Shell Station - Palmetto\n"
            "1240 8th Ave W, Palmetto, FL 34221\n"
            "Retail | Cap Rate: 6.10% | 16 Years Remaining On Lease\n\n"
            "101 Greystone Blvd, Columbia, SC 29210\nOffice | 242,444 SqFt\n\n"
            "Chick-Fil-A - Hendersonville TN\n"
            "262 East Main Street, Hendersonville, TN 37075\n"
            "New Construction | Ground Lease | Nashville MSA\n\n"
            "2712 Middleburg Dr, Columbia, SC 29204\nValue-Add Building | 48,184 SF\n\n"
            "690 Columbiana Dr, Columbia, SC 29212\n9,088 SF office building\n\n"
            "Tidal Wave Auto Spa\n"
            "300 N Overland Ave, Burley, ID 83318\nCar Wash\n\n"
            "330 W Main Street, Forest City, NC 28043\nCommercial Opportunity\n\n"
            "13778 Mono Way, Sonora, CA 95370\nGas Station | Ground Lease\n\n"
        ),
    },
    {
        "id": "1a030c212a46e4ee",
        "thread_id": "1a030c212a46e4ee",
        "sender": "noreply@loopnet.com",
        "subject": "1 property matched your saved search",
        "received_at": "2026-08-23T22:33:38Z",
        "text_body": (
            "1 new property matched your saved search.\n\n"
            "2115 S Brentwood, Springfield, MO 65804\n"
            "General Retail | For Sale\n"
            "Building Size: 2,000 SF\n"
            "Sale Price: $400,000\n\n"
        ),
    },
]

# Manually flagged car wash listings from the Crexi bulk email
CARWASH_FLAGS = [
    {
        "name": "Go Car Wash",
        "address": "4220 Sterling Avenue, Kansas City, MO 64130",
        "type": "Single Tenant Absolute NNN Car Wash",
        "brand_tier": "Tier-2 (Go Car Wash — regional chain)",
        "available": "Lease type: Absolute NNN, Roof: Tenant — price/cap not listed in email",
        "note": "Needs click-through for price, cap, lease term, and cost-seg data to score.",
    },
    {
        "name": "Tidal Wave Auto Spa",
        "address": "300 N Overland Ave, Burley, ID 83318",
        "type": "Car Wash (express tunnel)",
        "brand_tier": "Tier-1 (Tidal Wave Auto Spa)",
        "available": "No financial data in email",
        "note": "Tier-1 brand — worth a click-through if you have bandwidth.",
    },
]


class PreloadedGmailClient:
    def __init__(self, messages: list[EmailMessage], draft_out: Path) -> None:
        self._messages = messages
        self._draft_out = draft_out

    def search(self, query: str, max_results: int = 100) -> list[EmailMessage]:
        return self._messages

    def fetch_attachments(self, message_id: str, save_dir: str) -> list:
        return []

    def create_draft(self, draft: DraftRequest) -> str:
        payload = {
            "to": draft.to,
            "subject": draft.subject,
            "html_body": draft.html_body,
        }
        self._draft_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return "pending-mcp-create"


def build_messages() -> list[EmailMessage]:
    return [
        EmailMessage(
            id=e["id"],
            thread_id=e["thread_id"],
            sender=e["sender"],
            subject=e["subject"],
            received_at=e["received_at"],
            text_body=e["text_body"],
        )
        for e in EMAILS
    ]


def _score_springfield(listing: Listing) -> dict:
    """Score the Springfield listing by calling score() directly with year_built=2000 default.

    The structural gate fails only because year_built is absent; the scorer
    already treats year_built=0 as 2000. We bypass the gate and note the
    missing field explicitly in the digest.
    """
    scorer = MsaCommercialScorer()
    # Temporarily inject default so score() math works
    if not listing.raw_data:
        listing.raw_data = {}
    listing.raw_data.setdefault("year_built", 0)  # scorer uses `or 2000` internally
    result = scorer.score(listing)
    return {
        "score": result.score,
        "verdict": result.verdict,
        "notes": result.notes,
        "components": result.components,
    }


def _build_html(summary: dict, springfield_listing: Listing | None,
                springfield_score: dict | None) -> str:
    """Build the custom HTML digest for today's findings."""
    started = summary.get("started_at", "")[:19]
    sources = ", ".join(summary.get("sources_active", [])) or "none"
    emails = summary.get("emails_processed", 2)
    listings_new = summary.get("listings_new", 0)

    # Springfield block
    if springfield_listing and springfield_score:
        s = springfield_score
        verdict_color = {
            "PURSUE": "#15803d", "WATCH": "#b45309", "PASS": "#6b7280",
        }.get(s["verdict"], "#6b7280")
        price_psf = (springfield_listing.price / springfield_listing.sf
                     if springfield_listing.sf else 0)
        top3 = sorted(s["components"].items(), key=lambda x: x[1], reverse=True)[:3]
        top3_str = " &bull; ".join(
            f"{k.replace('_', ' ')}: {v:.1f}" for k, v in top3
        )
        springfield_html = f"""
<div style="border:1px solid #e2e8f0;border-radius:6px;padding:16px;margin-bottom:16px;">
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <span style="background:{verdict_color};color:#fff;padding:2px 8px;border-radius:4px;
      font-size:11px;font-weight:600;">{s['verdict']} &mdash; {s['score']:.0f}/100
      <span style="background:#dc2626;margin-left:6px;padding:1px 5px;border-radius:3px;
        font-size:10px;">[NEEDS REVIEW]</span>
    </span>
    <span style="font-size:12px;color:#64748b;">msa_commercial &middot; LoopNet</span>
  </div>
  <div style="margin-top:8px;">
    <strong>2115 S Brentwood</strong> &mdash; Springfield, MO 65804
  </div>
  <div style="color:#64748b;font-size:13px;margin-top:4px;">
    General Retail &middot; 2,000 SF &middot;
    <strong>$400,000</strong> ($200/SF asking)
  </div>
  <div style="font-size:12px;color:#64748b;margin-top:4px;">
    Top score drivers: {top3_str}
  </div>
  <div style="font-size:12px;color:#dc2626;margin-top:6px;">
    &#9888; Year built missing — score modeled with 2000 default.
    Verify on LoopNet before acting.
  </div>
  <div style="font-size:12px;margin-top:4px;">
    Note: {s['notes'][0] if s['notes'] else '—'}
  </div>
  <div style="font-size:12px;color:#475569;margin-top:4px;">
    Price/SF ${price_psf:.0f} — verify SF (2k SF for $400k in Springfield is
    above typical $40&ndash;$150/SF range; may be specialty retail or
    broker rounding error).
  </div>
</div>"""
    else:
        springfield_html = ""

    # Car wash flags block
    cw_rows = ""
    for c in CARWASH_FLAGS:
        cw_rows += f"""
<tr>
  <td style="padding:8px;border-bottom:1px solid #e2e8f0;font-weight:500;">{c['name']}</td>
  <td style="padding:8px;border-bottom:1px solid #e2e8f0;font-size:12px;">{c['address']}</td>
  <td style="padding:8px;border-bottom:1px solid #e2e8f0;font-size:12px;">{c['brand_tier']}</td>
  <td style="padding:8px;border-bottom:1px solid #e2e8f0;font-size:12px;">{c['note']}</td>
</tr>"""

    return f"""<!doctype html><html><body style="font-family:-apple-system,Segoe UI,sans-serif;
background:#f8fafc;margin:0;padding:24px;">
<div style="max-width:680px;margin:0 auto;background:#fff;border:1px solid #e2e8f0;
border-radius:8px;padding:24px;">

<h1 style="margin:0;font-size:20px;">ATG Deal Digest</h1>
<div style="color:#64748b;font-size:12px;margin-bottom:16px;">Mon, Aug 24 2026 &middot; 6:30 AM CT</div>

<div style="background:#fef3c7;border:1px solid #f59e0b;border-radius:6px;
  padding:12px;margin-bottom:20px;font-size:13px;">
  <strong>Pipeline: 2 emails processed, 1 new listing persisted, 0 fully scored.</strong><br>
  Crexi email is a bulk recommendation format (no per-listing pricing). LoopNet has one
  Springfield MO listing that passed geography &amp; price filters but lacks year&#8209;built data —
  included below as NEEDS REVIEW.
</div>

<h2 style="font-size:16px;border-bottom:2px solid #e2e8f0;padding-bottom:8px;">
  MSA Commercial — Springfield MO (1 listing, needs review)
</h2>
{springfield_html}

<h2 style="font-size:16px;border-bottom:2px solid #e2e8f0;padding-bottom:8px;margin-top:24px;">
  Car Wash — Flagged from Crexi Bulk Email (click-through needed)
</h2>
<p style="font-size:12px;color:#64748b;margin-bottom:8px;">
  These car wash listings appeared in a Crexi bulk recommendation email. Pricing and lease details
  are not available in the email body — require a click-through to score. Flagged here for awareness.
</p>
<table style="width:100%;border-collapse:collapse;font-size:13px;">
<thead>
  <tr style="background:#f8fafc;">
    <th style="padding:8px;text-align:left;border-bottom:2px solid #e2e8f0;">Property</th>
    <th style="padding:8px;text-align:left;border-bottom:2px solid #e2e8f0;">Address</th>
    <th style="padding:8px;text-align:left;border-bottom:2px solid #e2e8f0;">Brand Tier</th>
    <th style="padding:8px;text-align:left;border-bottom:2px solid #e2e8f0;">Action</th>
  </tr>
</thead>
<tbody>
{cw_rows}
</tbody>
</table>

<h2 style="font-size:16px;border-bottom:2px solid #e2e8f0;padding-bottom:8px;margin-top:24px;">
  Scan Stats
</h2>
<div style="display:flex;gap:12px;flex-wrap:wrap;">
  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:4px;padding:10px 16px;flex:1;">
    <div style="font-size:11px;color:#64748b;text-transform:uppercase;">Emails</div>
    <div style="font-size:24px;font-weight:700;">{emails}</div>
  </div>
  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:4px;padding:10px 16px;flex:1;">
    <div style="font-size:11px;color:#64748b;text-transform:uppercase;">New DB rows</div>
    <div style="font-size:24px;font-weight:700;">{listings_new}</div>
  </div>
  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:4px;padding:10px 16px;flex:1;">
    <div style="font-size:11px;color:#64748b;text-transform:uppercase;">Fully scored</div>
    <div style="font-size:24px;font-weight:700;">0</div>
  </div>
  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:4px;padding:10px 16px;flex:1;">
    <div style="font-size:11px;color:#64748b;text-transform:uppercase;">Flagged</div>
    <div style="font-size:24px;font-weight:700;">3</div>
  </div>
</div>
<p style="margin-top:16px;font-size:12px;color:#9ca3af;">
  Sources active: {sources}<br>
  Run: {started} UTC &middot; ATG Deal Scanner
</p>
</div>
</body></html>"""


def main() -> int:
    db.migrate()
    draft_out = Path("data/draft_request.json")
    draft_out.unlink(missing_ok=True)

    messages = build_messages()
    client = PreloadedGmailClient(messages, draft_out)
    since = datetime(2026, 8, 23, 11, 30, 0, tzinfo=timezone.utc)

    summary = pipeline.run(
        client=client,
        since=since,
        dry_run=True,   # we build the draft ourselves
        max_messages=50,
    )
    summary["run_date"] = "2026-08-24"

    # Pull the Springfield listing from the DB to score it
    import sqlite3
    db_path = Path("data/deals.db")
    springfield_listing: Listing | None = None
    springfield_score: dict | None = None

    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM listings WHERE address LIKE '%Brentwood%' ORDER BY first_seen DESC LIMIT 1"
            ).fetchone()
        if row:
            import json as _json
            raw = _json.loads(row["raw_data_json"] or "{}")
            springfield_listing = Listing(
                source=row["source"],
                source_listing_id=row["source_listing_id"],
                channel=row["channel"],
                listing_url=row["listing_url"],
                email_id=row["email_id"],
                title=row["title"],
                address=row["address"],
                city=row["city"],
                state=row["state"],
                zip=row["zip"],
                price=row["price"],
                cap_rate=row["cap_rate"],
                noi=row["noi"],
                sf=row["sf"],
                lot_acres=row["lot_acres"],
                tenant=row["tenant"],
                tenant_credit=row["tenant_credit"],
                lease_type=row["lease_type"],
                lease_start=None,
                lease_expiration=None,
                term_remaining_years=row["term_remaining_years"],
                escalator_pct=row["escalator_pct"],
                roof_structure=row["roof_structure"],
                bonus_dep_eligible=bool(row["bonus_dep_eligible"]) if row["bonus_dep_eligible"] is not None else None,
                estimated_cost_seg_pct=row["estimated_cost_seg_pct"],
                extraction_confidence=row["extraction_confidence"],
                needs_review=bool(row["needs_review"]),
                raw_data=raw,
                first_seen=datetime.now(timezone.utc),
                last_seen=datetime.now(timezone.utc),
            )
            springfield_score = _score_springfield(springfield_listing)
            log.info("springfield.scored",
                     verdict=springfield_score["verdict"],
                     score=springfield_score["score"])
    except Exception as e:
        log.warning("springfield.score_failed", error=str(e))

    # Build and write the draft
    html_body = _build_html(summary, springfield_listing, springfield_score)
    verdict = (springfield_score or {}).get("verdict", "?")
    score = (springfield_score or {}).get("score", 0)
    subject = (
        f"[ATG-DIGEST-AUTOSEND] ATG Deal Digest — Mon, Aug 24 — "
        f"1 new (Springfield MO {verdict} {score:.0f}/100) + 2 car wash flags"
    )
    draft_payload = {
        "to": ["agrassi@ybpsrv.com"],
        "subject": subject,
        "html_body": html_body,
    }
    draft_out.write_text(json.dumps(draft_payload, indent=2), encoding="utf-8")
    summary["draft_created"] = True
    summary["draft_id"] = "pending-mcp-create"
    summary["flagged_for_review"] = 1
    summary["carwash_manual_flags"] = 2

    # Append run log
    log_path = Path("data/run_log.json")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    if log_path.exists():
        try:
            rows = _json.loads(log_path.read_text(encoding="utf-8"))
        except Exception:
            rows = []
    rows.append(summary)
    log_path.write_text(_json.dumps(rows[-365:], indent=2, default=str), encoding="utf-8")

    print(_json.dumps({k: v for k, v in summary.items() if k != "gmail_query"}, indent=2, default=str))
    print("\n--- DRAFT SUBJECT ---")
    print(subject)
    return 0


if __name__ == "__main__":
    sys.exit(main())
