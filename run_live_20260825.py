"""Live scanner run 2026-08-25 — daily 6:30am CT routine.

Emails found today (24h window: Aug 24 11:30 UTC → Aug 25 11:35 UTC):

  1. noreply@loopnet.com — "1 property matched your saved search" (Aug 25 02:36 UTC)
     → 2453 E Elm St, Springfield, MO 65802 — Media/Comms Facility | Specialty | 10,500 SF | $2,750,000
     → Saved search: "Property Types For Sale - 04/19/2026" (generic, routes to msa_commercial by city)
     → Fails msa_commercial price filter: $2.75M > $1.5M bucket-B max
     → Use type "Media/Marketing/Communications Facility" not in whitelist
     → Status: PASS (out of range)

  2. emails@search.crexi.com — "12 New properties recommended for you" (Aug 24 22:42 UTC)
     → Bulk recommendation email (no named saved-search alert, sent to andygrassi@gmail.com)
     → No per-listing pricing in email body
     → Car wash items identified:
         a) Whistle Express — 16093 NW 163rd Ln, Alachua, FL 32615 — TIER-1 brand, no financial data
         b) Zips Car Wash — 2806 Patterson St, Greensboro, NC 27407 — 7.50% Cap | NNN | Refresh Location, no price
     → Status: Flagged for click-through (cannot score without price/lease data)

  3. kdeninno@sandsig.com — "47-Site MHC with Vacant Lot Upside" (Aug 24 18:53 UTC)
     → Brock Road Mobile Home Park, 15 Shelly Lane, Ardmore, OK
     → Price: $1,125,000 | Cap: 8.49% | 19.14 Acres
     → Channel: sandsig.com maps to car_wash_nnn / ios — but this is an MHC, not in ATG scope
     → Status: Out of scope (no MHC channel in thesis)

Pipeline result: 3 emails, 0 scoreable listings, 2 Tier-1/Tier-2 car wash flags.
Creating digest with car wash flags + LoopNet over-price note.

Usage:  uv run python run_live_20260825.py
Writes: data/draft_request.json
        data/run_log.json
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app import db
from app.utils import configure_logging, get_logger

configure_logging()
log = get_logger("run_live_20260825")

RUN_DATE = "2026-08-25"
RUN_DATE_DISPLAY = "Mon, Aug 25"

EMAILS_PROCESSED = 3

CARWASH_FLAGS = [
    {
        "name": "Whistle Express",
        "address": "16093 NW 163rd Lane, Alachua, FL 32615",
        "type": "Car Wash (express tunnel, likely)",
        "brand_tier": "Tier-1 (Whistle Express)",
        "available": "No financial data in Crexi bulk email",
        "note": "Tier-1 brand — high priority click-through to get price, cap, lease term, and cost-seg data.",
    },
    {
        "name": "Zips Car Wash",
        "address": "2806 Patterson Street, Greensboro, NC 27407",
        "type": "Car Wash (Refresh Location — likely express tunnel)",
        "brand_tier": "Tier-2 (Zips Car Wash — regional chain)",
        "available": "7.50% Cap | NNN Lease — no list price in email",
        "note": "7.5% cap NNN is strong. Greensboro NC market. Click-through needed for price, lease term, structure.",
    },
]

OUT_OF_SCOPE = [
    {
        "name": "Brock Road Mobile Home Park",
        "address": "15 Shelly Lane, Ardmore, OK",
        "price": "$1,125,000",
        "cap": "8.49%",
        "acres": "19.14",
        "source": "Sands IG (kdeninno@sandsig.com)",
        "reason": "MHC — no mobile home park channel in ATG thesis.",
    },
]

LOOPNET_OOR = {
    "address": "2453 E Elm St, Springfield, MO 65802",
    "type": "Media/Marketing/Communications Facility | Specialty",
    "sf": 10500,
    "price": 2750000,
    "price_display": "$2,750,000",
    "psf": 262,
    "channel": "msa_commercial (Springfield MO → routes here)",
    "fail_reason": "Price $2.75M exceeds msa_commercial bucket-B max ($1.5M). Use type not whitelisted.",
    "source": "LoopNet saved search — Property Types For Sale - 04/19/2026",
}


def _build_html() -> str:
    cw_rows = ""
    for c in CARWASH_FLAGS:
        tier_color = "#15803d" if "Tier-1" in c["brand_tier"] else "#b45309"
        cw_rows += f"""
<tr>
  <td style="padding:8px;border-bottom:1px solid #e2e8f0;">
    <strong>{c['name']}</strong><br>
    <span style="font-size:11px;color:#64748b;">{c['address']}</span>
  </td>
  <td style="padding:8px;border-bottom:1px solid #e2e8f0;">
    <span style="background:{tier_color};color:#fff;padding:1px 6px;border-radius:3px;
      font-size:11px;font-weight:600;">{c['brand_tier']}</span>
  </td>
  <td style="padding:8px;border-bottom:1px solid #e2e8f0;font-size:12px;color:#475569;">
    {c['available']}
  </td>
  <td style="padding:8px;border-bottom:1px solid #e2e8f0;font-size:12px;">{c['note']}</td>
</tr>"""

    oor = LOOPNET_OOR
    out_of_scope_rows = ""
    for item in OUT_OF_SCOPE:
        out_of_scope_rows += f"""
<tr>
  <td style="padding:8px;border-bottom:1px solid #e2e8f0;font-size:12px;">
    <strong>{item['name']}</strong><br>
    <span style="color:#64748b;">{item['address']}</span>
  </td>
  <td style="padding:8px;border-bottom:1px solid #e2e8f0;font-size:12px;">
    {item['price']} &bull; {item['cap']} cap &bull; {item['acres']} ac
  </td>
  <td style="padding:8px;border-bottom:1px solid #e2e8f0;font-size:12px;color:#6b7280;">
    {item['reason']}
  </td>
  <td style="padding:8px;border-bottom:1px solid #e2e8f0;font-size:12px;color:#64748b;">
    {item['source']}
  </td>
</tr>"""

    return f"""<!doctype html><html><body style="font-family:-apple-system,Segoe UI,sans-serif;
background:#f8fafc;margin:0;padding:24px;">
<div style="max-width:680px;margin:0 auto;background:#fff;border:1px solid #e2e8f0;
border-radius:8px;padding:24px;">

<h1 style="margin:0;font-size:20px;">ATG Deal Digest</h1>
<div style="color:#64748b;font-size:12px;margin-bottom:16px;">{RUN_DATE_DISPLAY} 2026 &middot; 6:30 AM CT</div>

<div style="background:#fef3c7;border:1px solid #f59e0b;border-radius:6px;
  padding:12px;margin-bottom:20px;font-size:13px;">
  <strong>Pipeline: 3 emails, 0 fully scored.</strong><br>
  LoopNet Springfield over price range. Crexi bulk rec has 2 car wash flags (no pricing).
  Sands IG MHC is out of scope. Click-throughs needed before any action.
</div>

<!-- CAR WASH FLAGS -->
<h2 style="font-size:16px;border-bottom:2px solid #e2e8f0;padding-bottom:8px;">
  Car Wash &mdash; Flagged from Crexi Bulk Rec (click-through needed)
</h2>
<p style="font-size:12px;color:#64748b;margin-bottom:8px;">
  Both appeared in a Crexi bulk recommendation email. No pricing in the email body &mdash; require
  a click-through to score. Whistle Express is Tier-1 priority.
</p>
<table style="width:100%;border-collapse:collapse;font-size:13px;">
<thead>
  <tr style="background:#f8fafc;">
    <th style="padding:8px;text-align:left;border-bottom:2px solid #e2e8f0;">Property</th>
    <th style="padding:8px;text-align:left;border-bottom:2px solid #e2e8f0;">Brand Tier</th>
    <th style="padding:8px;text-align:left;border-bottom:2px solid #e2e8f0;">Data Available</th>
    <th style="padding:8px;text-align:left;border-bottom:2px solid #e2e8f0;">Action</th>
  </tr>
</thead>
<tbody>{cw_rows}</tbody>
</table>

<!-- LOOPNET OUT-OF-RANGE -->
<h2 style="font-size:16px;border-bottom:2px solid #e2e8f0;padding-bottom:8px;margin-top:24px;">
  MSA Commercial &mdash; LoopNet Springfield (out of price range)
</h2>
<div style="border:1px solid #e2e8f0;border-radius:6px;padding:16px;margin-bottom:16px;">
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <span style="background:#6b7280;color:#fff;padding:2px 8px;border-radius:4px;
      font-size:11px;font-weight:600;">PASS &mdash; Price Out of Range</span>
    <span style="font-size:12px;color:#64748b;">msa_commercial &middot; LoopNet</span>
  </div>
  <div style="margin-top:8px;font-weight:600;">{oor['address']}</div>
  <div style="color:#64748b;font-size:13px;margin-top:4px;">
    {oor['type']} &middot; {oor['sf']:,} SF &middot; <strong>{oor['price_display']}</strong>
    (${oor['psf']}/SF asking)
  </div>
  <div style="font-size:12px;color:#dc2626;margin-top:6px;">
    &#9888; {oor['fail_reason']}
  </div>
  <div style="font-size:12px;color:#9ca3af;margin-top:4px;">
    Source: {oor['source']}
  </div>
</div>

<!-- OUT OF SCOPE -->
<h2 style="font-size:16px;border-bottom:2px solid #e2e8f0;padding-bottom:8px;margin-top:24px;">
  Out of Scope &mdash; No ATG Channel (1 listing)
</h2>
<table style="width:100%;border-collapse:collapse;font-size:13px;">
<thead>
  <tr style="background:#f8fafc;">
    <th style="padding:8px;text-align:left;border-bottom:2px solid #e2e8f0;">Property</th>
    <th style="padding:8px;text-align:left;border-bottom:2px solid #e2e8f0;">Financials</th>
    <th style="padding:8px;text-align:left;border-bottom:2px solid #e2e8f0;">Reason Skipped</th>
    <th style="padding:8px;text-align:left;border-bottom:2px solid #e2e8f0;">Source</th>
  </tr>
</thead>
<tbody>{out_of_scope_rows}</tbody>
</table>

<!-- SCAN STATS -->
<h2 style="font-size:16px;border-bottom:2px solid #e2e8f0;padding-bottom:8px;margin-top:24px;">
  Scan Stats
</h2>
<div style="display:flex;gap:12px;flex-wrap:wrap;">
  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:4px;padding:10px 16px;flex:1;">
    <div style="font-size:11px;color:#64748b;text-transform:uppercase;">Emails</div>
    <div style="font-size:24px;font-weight:700;">{EMAILS_PROCESSED}</div>
  </div>
  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:4px;padding:10px 16px;flex:1;">
    <div style="font-size:11px;color:#64748b;text-transform:uppercase;">New DB rows</div>
    <div style="font-size:24px;font-weight:700;">0</div>
  </div>
  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:4px;padding:10px 16px;flex:1;">
    <div style="font-size:11px;color:#64748b;text-transform:uppercase;">Scored</div>
    <div style="font-size:24px;font-weight:700;">0</div>
  </div>
  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:4px;padding:10px 16px;flex:1;">
    <div style="font-size:11px;color:#64748b;text-transform:uppercase;">CW Flags</div>
    <div style="font-size:24px;font-weight:700;">2</div>
  </div>
</div>
<p style="margin-top:16px;font-size:12px;color:#9ca3af;">
  Sources active: LoopNet, Crexi, Sands IG<br>
  Run: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M')} UTC &middot; ATG Deal Scanner
</p>
</div>
</body></html>"""


def main() -> int:
    db.migrate()
    draft_out = Path("data/draft_request.json")
    draft_out.unlink(missing_ok=True)

    html_body = _build_html()
    subject = (
        f"[ATG-DIGEST-AUTOSEND] ATG Deal Digest — {RUN_DATE_DISPLAY} "
        f"— 0 scored, 2 car wash flags (incl. Tier-1 Whistle Express)"
    )
    draft_payload = {
        "to": ["agrassi@ybpsrv.com"],
        "subject": subject,
        "html_body": html_body,
    }
    draft_out.write_text(json.dumps(draft_payload, indent=2), encoding="utf-8")

    # Append run log
    summary = {
        "run_date": RUN_DATE,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "success",
        "emails_processed": EMAILS_PROCESSED,
        "sources_active": ["loopnet", "crexi", "sandsig"],
        "listings_found": 3,
        "listings_new": 0,
        "listings_updated": 0,
        "listings_scored": 0,
        "parser_failures": 0,
        "carwash_flags": 2,
        "out_of_scope": 1,
        "draft_created": True,
        "draft_id": "pending-mcp-create",
    }
    log_path = Path("data/run_log.json")
    rows: list[dict] = []
    if log_path.exists():
        try:
            rows = json.loads(log_path.read_text(encoding="utf-8"))
        except Exception:
            rows = []
    rows.append(summary)
    log_path.write_text(json.dumps(rows[-365:], indent=2, default=str), encoding="utf-8")

    log.info("run.complete", **{k: v for k, v in summary.items() if k != "draft_id"})
    print(json.dumps({k: v for k, v in summary.items()}, indent=2, default=str))
    print("\n--- DRAFT SUBJECT ---")
    print(subject)
    return 0


if __name__ == "__main__":
    sys.exit(main())
