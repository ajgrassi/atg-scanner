"""Live scanner run 2026-08-26 — daily 6:30am CT routine.

Emails found today (24h window: Aug 25 11:30 UTC → Aug 26 11:35 UTC):

  1. emails@search.crexi.com → "12 New properties recommended for you" (Aug 25 22:46 UTC)
     → Bulk recommendation email, no named saved-search alert
     → Sent to andygrassi@gmail.com (not the primary agrassi@ybpsrv.com address)
     → Properties scanned: 12 total; 3 car washes identified:
         a) Whistle Express Wash — 62 Moore Dr, Southaven, MS 38671
            6.50% CAP | 1,980 SqFt | Tier-1 brand | NO price in email
         b) Abs. Net Whistle Express Car Wash — 701 W Ridge Road, Pharr, TX 78577
            Abs. NNN | 100% Bonus Dep | Tier-1 brand | NO cap/price in email
         c) Gleaux Car Wash — 2017 S Broadway Ave, Tyler, TX 75701
            Unknown brand | NO financial data in email
     → Routing: subject doesn't match any saved-search name → msa_commercial default
     → msa_commercial filter: none of these properties are in MO → all PASS (out of scope)
     → Status: 3 car wash flags (click-through needed for pricing)

  2. lkortava@sandsig.com → "New Listing | 100% Occupied Retail Plaza | 7.28% CAP |
     Below-Market | 39,846 SF | Fayetteville, NC" (Aug 25 17:03 UTC)
     → Pamalee Plaza, Murchison Road, Fayetteville, NC
     → Price: $3,300,000 | CAP: 7.28% | SF: 39,846
     → Parser: SandsIgParser → no street number found ("along Murchison Road")
       → parser failure (address pattern requires digit-leading street number)
     → Channel from SOURCES: car_wash_nnn / ios
     → Multi-tenant retail plaza with 4 tenants, all below-market leases
     → Not a car wash, not IOS → out of scope for ATG thesis
     → Status: PARSER FAILURE + out of scope

Pipeline result: 2 emails, 0 scoreable listings, 3 car wash flags (Tier-1 priority),
1 parser failure, 1 out-of-scope.
Creating digest with car wash flags + Sands IG out-of-scope note.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app import db
from app.utils import configure_logging, get_logger

configure_logging()
log = get_logger("run_live_20260826")

RUN_DATE = "2026-08-26"
RUN_DATE_DISPLAY = "Wed, Aug 26"
EMAILS_PROCESSED = 2


def _build_html() -> str:
    car_washes = [
        {
            "brand": "Whistle Express Wash",
            "address": "62 Moore Dr, Southaven, MS 38671",
            "tier": "Tier-1 (Mister/Whistle/Take 5 family)",
            "data": "6.50% CAP | 1,980 SF",
            "note": "No price in email — click through on Crexi to get OM",
            "action": "⭐ Priority click-through",
        },
        {
            "brand": "Abs. Net Whistle Express Car Wash",
            "address": "701 W Ridge Road, Pharr, TX 78577",
            "tier": "Tier-1 (Mister/Whistle/Take 5 family)",
            "data": "Absolute NNN | 100% Bonus Dep eligible",
            "note": "No price/cap in email — click through on Crexi to get OM",
            "action": "⭐ Priority click-through",
        },
        {
            "brand": "Gleaux Car Wash",
            "address": "2017 S Broadway Ave, Tyler, TX 75701",
            "tier": "Unknown / Regional brand",
            "data": "No financial data in email",
            "note": "No data available — click through for details",
            "action": "Low priority",
        },
    ]

    cw_rows = ""
    for cw in car_washes:
        bg = "#fef9c3" if "⭐" in cw["action"] else "#f8fafc"
        cw_rows += f"""
<tr style="background:{bg};">
  <td style="padding:10px 8px;border-bottom:1px solid #e2e8f0;">
    <div style="font-weight:600;">{cw['brand']}</div>
    <div style="color:#64748b;font-size:12px;">{cw['address']}</div>
  </td>
  <td style="padding:10px 8px;border-bottom:1px solid #e2e8f0;font-size:12px;">{cw['tier']}</td>
  <td style="padding:10px 8px;border-bottom:1px solid #e2e8f0;font-size:12px;">{cw['data']}</td>
  <td style="padding:10px 8px;border-bottom:1px solid #e2e8f0;font-size:12px;">
    <div style="font-weight:600;">{cw['action']}</div>
    <div style="color:#64748b;">{cw['note']}</div>
  </td>
</tr>"""

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M UTC")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ATG Deal Digest — {RUN_DATE_DISPLAY}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         font-size: 14px; color: #1e293b; max-width: 700px; margin: 0 auto; padding: 20px; }}
  h1 {{ font-size: 20px; margin-bottom: 4px; }}
  h2 {{ font-size: 16px; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; margin-top: 24px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ padding: 8px; text-align: left; border-bottom: 2px solid #e2e8f0; background: #f8fafc; }}
</style>
</head>
<body>
<h1>ATG Deal Digest &mdash; {RUN_DATE_DISPLAY}</h1>
<p style="color:#64748b;font-size:12px;margin-top:4px;">{now_str} &middot; ATG Deal Scanner</p>

<div style="background:#fef3c7;border:1px solid #f59e0b;border-radius:6px;
  padding:12px;margin-bottom:20px;font-size:13px;">
  <strong>Pipeline: 2 emails, 0 scored, 3 car wash flags (incl. 2 Tier-1 Whistle Express),
  1 parser failure.</strong><br>
  Click-throughs needed on the two Whistle Express properties before scoring.
  Sands IG retail plaza (Pamalee, Fayetteville NC) is out of ATG scope.
</div>

<!-- CAR WASH FLAGS -->
<h2>Car Wash &mdash; Flagged from Crexi Bulk Recommendations (click-through needed)</h2>
<p style="font-size:12px;color:#64748b;margin-bottom:8px;">
  All three appeared in a Crexi bulk recommendation email (not a named saved-search alert).
  No pricing is embedded &mdash; requires a click-through to Crexi to get the OM.
  The two Whistle Express locations are Tier-1 priority per ATG brand scoring.
</p>
<table>
<thead>
  <tr>
    <th>Brand / Address</th>
    <th>Brand Tier</th>
    <th>Data in Email</th>
    <th>Action</th>
  </tr>
</thead>
<tbody>{cw_rows}
</tbody>
</table>

<!-- OUT OF SCOPE -->
<h2>Out of Scope &mdash; Sands IG Retail Plaza (1 listing)</h2>
<div style="border:1px solid #e2e8f0;border-radius:6px;padding:16px;margin-bottom:16px;">
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <span style="background:#6b7280;color:#fff;padding:2px 8px;border-radius:4px;
      font-size:11px;font-weight:600;">OUT OF SCOPE</span>
    <span style="font-size:12px;color:#64748b;">sands_ig &middot; PARSER FAILURE</span>
  </div>
  <div style="margin-top:8px;font-weight:600;">Pamalee Plaza &mdash; Fayetteville, NC (Cumberland County)</div>
  <div style="color:#64748b;font-size:13px;margin-top:4px;">
    Multi-tenant retail | 39,846 SF | <strong>$3,300,000</strong> | 7.28% CAP | 100% occupied | 4 tenants, below-market leases
  </div>
  <div style="font-size:12px;color:#dc2626;margin-top:6px;">
    &#9888; Parser failure: address pattern requires a digit-leading street number;
    email body only says &ldquo;along Murchison Road&rdquo;. Also not in ATG channels
    (not a car wash, not IOS, not MO commercial).
  </div>
  <div style="font-size:12px;color:#9ca3af;margin-top:4px;">
    Broker: Lasha Kortava, Sands Investment Group &mdash; lkortava@SandsIG.com / 404.207.1171
  </div>
</div>

<!-- SCAN STATS -->
<h2>Scan Stats</h2>
<div style="display:flex;gap:12px;flex-wrap:wrap;">
  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:4px;padding:10px 16px;flex:1;min-width:80px;">
    <div style="font-size:11px;color:#64748b;text-transform:uppercase;">Emails</div>
    <div style="font-size:24px;font-weight:700;">{EMAILS_PROCESSED}</div>
  </div>
  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:4px;padding:10px 16px;flex:1;min-width:80px;">
    <div style="font-size:11px;color:#64748b;text-transform:uppercase;">Scored</div>
    <div style="font-size:24px;font-weight:700;">0</div>
  </div>
  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:4px;padding:10px 16px;flex:1;min-width:80px;">
    <div style="font-size:11px;color:#64748b;text-transform:uppercase;">CW Flags</div>
    <div style="font-size:24px;font-weight:700;">3</div>
  </div>
  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:4px;padding:10px 16px;flex:1;min-width:80px;">
    <div style="font-size:11px;color:#64748b;text-transform:uppercase;">Parser Failures</div>
    <div style="font-size:24px;font-weight:700;">1</div>
  </div>
</div>
<p style="margin-top:16px;font-size:12px;color:#9ca3af;">
  Sources active: Crexi (bulk rec), Sands IG<br>
  Run: {now_str} &middot; ATG Deal Scanner
</p>

</body>
</html>"""


def main() -> int:
    db.migrate()
    draft_out = Path("data/draft_request.json")
    draft_out.unlink(missing_ok=True)

    html_body = _build_html()
    subject = (
        f"[ATG-DIGEST-AUTOSEND] ATG Deal Digest — {RUN_DATE_DISPLAY} "
        f"— 0 scored, 3 car wash flags (incl. 2 Tier-1 Whistle Express)"
    )
    draft_payload = {
        "to": ["agrassi@ybpsrv.com"],
        "subject": subject,
        "html_body": html_body,
    }
    draft_out.write_text(json.dumps(draft_payload, indent=2), encoding="utf-8")

    summary = {
        "run_date": RUN_DATE,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "success",
        "emails_processed": EMAILS_PROCESSED,
        "sources_active": ["crexi", "sandsig"],
        "listings_found": 1,
        "listings_new": 0,
        "listings_updated": 0,
        "listings_scored": 0,
        "parser_failures": 1,
        "carwash_flags": 3,
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
    print(json.dumps(summary, indent=2, default=str))
    print("\n--- DRAFT SUBJECT ---")
    print(subject)
    return 0


if __name__ == "__main__":
    sys.exit(main())
