"""Live scanner run 2026-09-14 — daily 6:30am CT routine.

Email found today (24h window: Sep 13 11:30 UTC → Sep 14 11:30 UTC):

  1. emails@search.crexi.com → "12 New properties recommended for you" (Sep 13 21:29 UTC)
     → Bulk recommendation email, no named saved-search alert
     → Sent to andygrassi@gmail.com
     → 12 properties total; 5 car washes identified:
         a) Zips Car Wash — 4416 Western Ave, Knoxville, TN 37921
            6.75% CAP | 3,003 SqFt | Tier-2 (Zips) | No price in email
         b) WOW Carwash - Blue Diamond & Durango — 9280 S Durango Dr, Las Vegas, NV 89178
            20-Year Absolute NNN Lease | No price/cap in email
         c) NNN MISTER CAR WASH - Canton GA — 651 Riverstone Pkwy, Canton, GA 30114
            6.50% CAP | 4,036 SqFt | Tier-1 (Mister) | No price in email
         d) High-Performing Whistle Express — 5011 Ramsey St, Fayetteville, NC 28311
            16 Yrs Remaining | 1.50% Annual Bump (next Dec 2026) | Tier-1 | No price/cap
         e) Whistle Express — 11380 Bloomingdale Ave, Riverview, FL 33578
            Tier-1 | No financial data in email
     → 7 out-of-scope: offices/retail/land in Columbia SC, Irmo SC, Lexington SC

Pipeline result: 1 email, 5 car wash flags (incl. 3 Tier-1 properties),
7 out-of-scope. 0 formally scored listings (no saved-search routing keyword).
Creating digest with car wash flags.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app import db
from app.utils import configure_logging, get_logger

configure_logging()
log = get_logger("run_live_20260914")

RUN_DATE = "2026-09-14"
RUN_DATE_DISPLAY = "Sun, Sep 14"
EMAILS_PROCESSED = 1


def _build_html() -> str:
    car_washes = [
        {
            "brand": "NNN MISTER CAR WASH — Canton, GA",
            "address": "651 Riverstone Pkwy, Canton, GA 30114",
            "tier": "Tier-1 (Mister Car Wash)",
            "data": "6.50% CAP | 4,036 SF | Special Purpose",
            "note": "No price in email — click through on Crexi to get OM",
            "action": "⭐ Priority click-through",
            "priority": 1,
        },
        {
            "brand": "Whistle Express — Fayetteville, NC",
            "address": "5011 Ramsey St, Fayetteville, NC 28311",
            "tier": "Tier-1 (Whistle Express)",
            "data": "16 Yrs Remaining | 1.50% Annual Rent Bump (next Dec 2026)",
            "note": "No price/cap in email — click through for full OM",
            "action": "⭐ Priority click-through",
            "priority": 2,
        },
        {
            "brand": "Whistle Express — Riverview, FL",
            "address": "11380 Bloomingdale Ave, Riverview, FL 33578",
            "tier": "Tier-1 (Whistle Express)",
            "data": "No financial data in email",
            "note": "Brand-only flag — click through for details",
            "action": "⭐ Click-through (Tier-1 brand)",
            "priority": 3,
        },
        {
            "brand": "Zips Car Wash — Knoxville, TN",
            "address": "4416 Western Ave, Knoxville, TN 37921",
            "tier": "Tier-2 (Zips / Club Car Wash)",
            "data": "6.75% CAP | 3,003 SF | Recent 2025 Remodel",
            "note": "No price in email — click through; 6.75% CAP is above ATG threshold",
            "action": "Click-through (solid CAP rate)",
            "priority": 4,
        },
        {
            "brand": "WOW Carwash — Las Vegas, NV",
            "address": "9280 S Durango Dr, Las Vegas, NV 89178",
            "tier": "Regional brand",
            "data": "20-Year Absolute NNN Lease",
            "note": "Long lease term, but WOW is not in ATG Tier-1/Tier-2 list; review if priced right",
            "action": "Low priority (regional brand)",
            "priority": 5,
        },
    ]

    cw_rows = ""
    for cw in car_washes:
        bg = "#fef9c3" if "⭐" in cw["action"] else "#f8fafc"
        priority_badge = f'<span style="background:#1e40af;color:#fff;padding:1px 6px;border-radius:3px;font-size:10px;margin-right:6px;">#{cw["priority"]}</span>'
        cw_rows += f"""
<tr style="background:{bg};">
  <td style="padding:10px 8px;border-bottom:1px solid #e2e8f0;">
    <div style="font-weight:600;">{priority_badge}{cw['brand']}</div>
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
<title>ATG Deal Digest &mdash; {RUN_DATE_DISPLAY}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         font-size: 14px; color: #1e293b; max-width: 700px; margin: 0 auto; padding: 20px; }}
  h1 {{ font-size: 20px; margin-bottom: 4px; }}
  h2 {{ font-size: 16px; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; margin-top: 24px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ padding: 8px; text-align: left; border-bottom: 2px solid #e2e8f0; background: #f8fafc; }}
  @media (max-width: 480px) {{
    table {{ font-size: 11px; }}
    th, td {{ padding: 6px 4px !important; }}
  }}
</style>
</head>
<body>
<h1>ATG Deal Digest &mdash; {RUN_DATE_DISPLAY}</h1>
<p style="color:#64748b;font-size:12px;margin-top:4px;">{now_str} &middot; ATG Deal Scanner</p>

<div style="background:#fef3c7;border:1px solid #f59e0b;border-radius:6px;
  padding:12px;margin-bottom:20px;font-size:13px;">
  <strong>Pipeline: 1 email, 5 car wash flags (3 Tier-1), 0 formally scored.</strong><br>
  Crexi bulk recommendation email (no saved-search routing). Click-throughs needed to score the three
  Tier-1 properties. Zips has a solid 6.75% CAP worth checking. 7 other listings were out-of-scope
  (offices + land in Columbia SC, Irmo SC, Lexington SC).
</div>

<!-- CAR WASH FLAGS -->
<h2>Car Wash &mdash; 5 Flagged from Crexi Bulk Recommendations</h2>
<p style="font-size:12px;color:#64748b;margin-bottom:8px;">
  All five appeared in a Crexi bulk recommendation email to andygrassi@gmail.com (not a named
  saved-search alert). No pricing is embedded in the email &mdash; requires click-through to Crexi
  for OMs. Three Tier-1 brands are priority click-throughs per ATG car wash scoring.
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
<h2>Out of Scope &mdash; 7 Listings (SC / NV Offices &amp; Land)</h2>
<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:12px;
  font-size:13px;color:#475569;">
  These properties are outside ATG investment thesis (not MO commercial, not car wash, not storage,
  not IOS, not O&amp;G, not solar):
  <ul style="margin:8px 0 0 0;padding-left:18px;line-height:1.8;">
    <li>7700 Trenholm Road Ext, Columbia, SC 29223 (Office/Commercial)</li>
    <li>117 Alpine Circle, Columbia, SC 29223 (Office, 11,109 SF)</li>
    <li>2757-2761 Rosewood Dr, Columbia, SC 29205</li>
    <li>Freestanding Retail/Medical Office &mdash; 7211 Broad River Rd, Irmo, SC 29063</li>
    <li>Two Notch Commercial &mdash; 1000 Two Notch Rd, Lexington, SC 29073 (Land)</li>
    <li>925 Gervais St. &amp; 1217 Park St, Columbia, SC 29201 (Retail)</li>
    <li>1621-1623 Main St, Columbia, SC 29201 (Investment Property)</li>
  </ul>
</div>

<!-- SCAN STATS -->
<h2>Scan Stats</h2>
<div style="display:flex;gap:12px;flex-wrap:wrap;">
  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:4px;padding:10px 16px;flex:1;min-width:80px;">
    <div style="font-size:11px;color:#64748b;text-transform:uppercase;">Emails</div>
    <div style="font-size:24px;font-weight:700;">{EMAILS_PROCESSED}</div>
  </div>
  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:4px;padding:10px 16px;flex:1;min-width:80px;">
    <div style="font-size:11px;color:#64748b;text-transform:uppercase;">CW Flags</div>
    <div style="font-size:24px;font-weight:700;">5</div>
  </div>
  <div style="background:#fef9c3;border:1px solid #f59e0b;border-radius:4px;padding:10px 16px;flex:1;min-width:80px;">
    <div style="font-size:11px;color:#92400e;text-transform:uppercase;">Tier-1 Flags</div>
    <div style="font-size:24px;font-weight:700;">3</div>
  </div>
  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:4px;padding:10px 16px;flex:1;min-width:80px;">
    <div style="font-size:11px;color:#64748b;text-transform:uppercase;">Out of Scope</div>
    <div style="font-size:24px;font-weight:700;">7</div>
  </div>
  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:4px;padding:10px 16px;flex:1;min-width:80px;">
    <div style="font-size:11px;color:#64748b;text-transform:uppercase;">Scored</div>
    <div style="font-size:24px;font-weight:700;">0</div>
  </div>
</div>
<p style="margin-top:16px;font-size:12px;color:#9ca3af;">
  Sources active: Crexi (bulk rec)<br>
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
        f"— 5 car wash flags (3 Tier-1: Mister CW, Whistle x2)"
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
        "sources_active": ["crexi"],
        "listings_found": 5,
        "listings_new": 0,
        "listings_updated": 0,
        "listings_scored": 0,
        "parser_failures": 0,
        "carwash_flags": 5,
        "tier1_flags": 3,
        "out_of_scope": 7,
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
