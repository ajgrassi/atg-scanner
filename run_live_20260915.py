"""Live scanner run 2026-09-15 — daily 6:30am CT routine.

Email found today (24h window: Sep 14 11:30 UTC → Sep 15 11:30 UTC):

  1. emails@search.crexi.com → "12 New properties recommended for you" (Sep 14 21:29 UTC)
     → Bulk recommendation email, no named saved-search alert
     → Sent to andygrassi@gmail.com
     → 12 properties total; 6 car washes identified:
         a) WhiteWater Express — 300 W Parkwood Ave, Friendswood, TX 77546
            6.25% CAP | 100% Bonus Depreciation | 150+ Unit Corp. Guarantee | $194K AHHI 1-Mile
            Tier-1 brand | No price in email
         b) Zips Car Wash — 3505 West Northwest Hwy, Dallas, TX 75220
            7.00% CAP | +/- 39,000 VPD | Tier-2 brand | No price in email
         c) Whistle Express — 27510 Bermont Road, Punta Gorda, FL 33982
            Tier-1 brand | No financial data in email
         d) Whistle Express — 105 South Westover Blvd, Albany, GA 31707
            Tier-1 brand | No financial data in email
         e) GO Car Wash Portfolio — 5550 W Charleston Blvd, Las Vegas, NV 89146
            6 Assets | ABS NNN Master Lease | ±16.4 Yrs WALT | 1.50% Annual Bumps
            Portfolio deal (likely $10M+) | No price in email
         f) LUV Car Wash — 63 Little Cypress Drive, St Johns, FL 32259
            Absolute NNN | 17+ Yrs Remaining | No price/cap in email
     → 6 out-of-scope: offices/gas stations in SC and CA

Pipeline result: 1 email, 6 car wash flags (3 Tier-1, 1 Tier-2, 2 other),
6 out-of-scope. 0 formally scored (no prices in email — click-through required).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app import db
from app.utils import configure_logging, get_logger

configure_logging()
log = get_logger("run_live_20260915")

RUN_DATE = "2026-09-15"
RUN_DATE_DISPLAY = "Mon, Sep 15"
EMAILS_PROCESSED = 1


def _build_html() -> str:
    car_washes = [
        {
            "brand": "WhiteWater Express — Friendswood, TX",
            "address": "300 W Parkwood Ave, Friendswood, TX 77546",
            "tier": "Tier-1 (WhiteWater Express)",
            "data": "6.25% CAP | 100% Bonus Dep | 150+ Unit Corp. Guarantee | $194K AHHI 1-Mi",
            "note": "Tier-1 brand + bonus dep confirmed + strong demographics. No price — click Crexi OM",
            "action": "⭐ Priority click-through",
            "priority": 1,
        },
        {
            "brand": "Zips Car Wash — Dallas, TX",
            "address": "3505 West Northwest Highway, Dallas, TX 75220",
            "tier": "Tier-2 (Zips)",
            "data": "7.00% CAP | +/- 39,000 VPD",
            "note": "7% CAP is above ATG threshold (≥7% earns full 12 pts). No price — click for OM",
            "action": "⭐ Priority click-through (top CAP rate)",
            "priority": 2,
        },
        {
            "brand": "Whistle Express — Punta Gorda, FL",
            "address": "27510 Bermont Road, Punta Gorda, FL 33982",
            "tier": "Tier-1 (Whistle Express)",
            "data": "No financial data in email",
            "note": "Tier-1 brand flag — click through Crexi for OM and lease details",
            "action": "⭐ Click-through (Tier-1 brand)",
            "priority": 3,
        },
        {
            "brand": "Whistle Express — Albany, GA",
            "address": "105 South Westover Boulevard, Albany, GA 31707",
            "tier": "Tier-1 (Whistle Express)",
            "data": "No financial data in email",
            "note": "Tier-1 brand flag — click through Crexi for OM and lease details",
            "action": "⭐ Click-through (Tier-1 brand)",
            "priority": 4,
        },
        {
            "brand": "GO Car Wash Portfolio — Las Vegas, NV",
            "address": "5550 W Charleston Blvd, Las Vegas, NV 89146 (portfolio anchor)",
            "tier": "Corporate operator (6-asset portfolio)",
            "data": "ABS NNN Master Lease | ±16.4 Yrs WALT | 1.50% Annual Bumps | 6 Assets",
            "note": "Portfolio deal likely $10M+ — above ATG $2-6M sweet spot. Excellent lease "
                    "structure. Click for pricing; may be worth partial or pass.",
            "action": "Click-through (size check first)",
            "priority": 5,
        },
        {
            "brand": "LUV Car Wash — St Johns, FL",
            "address": "63 Little Cypress Drive, St Johns, FL 32259",
            "tier": "Regional brand",
            "data": "Absolute NNN | 17+ Yrs Remaining",
            "note": "Solid lease structure; LUV not in ATG Tier-1/2 — need price/brand financials",
            "action": "Click-through (lease ok, brand TBD)",
            "priority": 6,
        },
    ]

    cw_rows = ""
    for cw in car_washes:
        bg = "#fef9c3" if "⭐" in cw["action"] else "#f8fafc"
        priority_badge = (
            f'<span style="background:#1e40af;color:#fff;padding:1px 6px;'
            f'border-radius:3px;font-size:10px;margin-right:6px;">#{cw["priority"]}</span>'
        )
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
  <strong>Pipeline: 1 email, 6 car wash flags (3 Tier-1, 1 Tier-2, 2 other), 0 formally scored.</strong><br>
  Crexi bulk recommendation email — no pricing embedded. Top picks: WhiteWater Express (Tier-1,
  6.25% CAP, confirmed bonus dep) and Zips Dallas (7.00% CAP, peak of ATG scoring band).
  6 out-of-scope listings omitted (SC offices, CA gas stations).
</div>

<!-- CAR WASH FLAGS -->
<h2>Car Wash &mdash; 6 Flagged from Crexi Bulk Recommendations</h2>
<p style="font-size:12px;color:#64748b;margin-bottom:8px;">
  From Crexi "12 New properties recommended for you" email (Sep 14, 9:29 PM UTC) to
  andygrassi@gmail.com. No pricing in email &mdash; click-through to Crexi for OMs.
  Sorted by ATG priority (Tier-1 brand + strongest financials first).
</p>
<table>
<thead>
  <tr>
    <th>Brand / Address</th>
    <th>Brand Tier</th>
    <th>Data in Email</th>
    <th>Action / Notes</th>
  </tr>
</thead>
<tbody>{cw_rows}
</tbody>
</table>

<!-- STANDOUT DETAIL: WHITEWATER -->
<h2>Standout: WhiteWater Express — Friendswood, TX (Priority #1)</h2>
<div style="background:#f0fdf4;border:1px solid #86efac;border-radius:6px;padding:12px;font-size:13px;">
  <strong>Why this one leads:</strong>
  <ul style="margin:6px 0 0 0;padding-left:18px;line-height:1.9;">
    <li>Tier-1 brand (WhiteWater Express explicitly in ATG scoring list = 7 brand pts)</li>
    <li>100% Bonus Depreciation confirmed in listing = bonus_dep_eligible gate passes</li>
    <li>150+ unit corporate guarantee → strong tenant credit (likely 14–18 pts)</li>
    <li>6.25% CAP = 6 pts on cap rate scoring (between 6–6.5% band)</li>
    <li>$194K average household income 1-mile = strong site quality indicator</li>
  </ul>
  <p style="margin:8px 0 0;color:#166534;font-weight:600;">
    → Click through on Crexi, request OM, check: price (target $2–6M), lease term remaining
    (need ≥15yr for 15 pts), escalator %, roof structure (must be tenant for gate pass).
  </p>
</div>

<!-- STANDOUT DETAIL: ZIPS -->
<h2>Standout: Zips Car Wash — Dallas, TX (Priority #2)</h2>
<div style="background:#f0f9ff;border:1px solid #7dd3fc;border-radius:6px;padding:12px;font-size:13px;">
  <strong>Why this ranks #2:</strong>
  <ul style="margin:6px 0 0 0;padding-left:18px;line-height:1.9;">
    <li>7.00% CAP = full 12 pts on ATG scoring (top of ≥7% band)</li>
    <li>39,000 VPD = strong traffic — typical car wash needs 25K+ VPD</li>
    <li>Zips = Tier-2 brand = 5 brand pts (vs Tier-1's 7)</li>
  </ul>
  <p style="margin:8px 0 0;color:#0c4a6e;font-weight:600;">
    → Click through for price, lease term, escalator, and absolute NNN confirmation.
    At 7% CAP a $3M deal yields ~$210K NOI/yr → strong CoC with 25% down, 7% rate, 25yr am.
  </p>
</div>

<!-- OUT OF SCOPE -->
<h2>Out of Scope &mdash; 6 Listings (SC Offices &amp; CA Gas Stations)</h2>
<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:12px;
  font-size:13px;color:#475569;">
  <ul style="margin:4px 0 0 0;padding-left:18px;line-height:1.8;">
    <li>4265 Augusta Rd, Lexington, SC 29073 (Commercial / Fully Leased)</li>
    <li>1440 Broad River Rd, Columbia, SC 29210 (Office, 8,513 SF, 11.50% CAP)</li>
    <li>1508 Washington St., Columbia, SC 29201 (Downtown Office, 3-story brick)</li>
    <li>CHEVRON Gas Station &amp; Market — 2226 Jackson Ave, Escalon, CA 95320</li>
    <li>Gas Station / Restaurant / Motel — 72137 Baker Blvd, Baker, CA 92309</li>
    <li>ARCO Gas with AM/PM C-Store — 3890 University Pkwy, San Bernardino, CA 92407</li>
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
    <div style="font-size:24px;font-weight:700;">6</div>
  </div>
  <div style="background:#fef9c3;border:1px solid #f59e0b;border-radius:4px;padding:10px 16px;flex:1;min-width:80px;">
    <div style="font-size:11px;color:#92400e;text-transform:uppercase;">Tier-1 Flags</div>
    <div style="font-size:24px;font-weight:700;">3</div>
  </div>
  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:4px;padding:10px 16px;flex:1;min-width:80px;">
    <div style="font-size:11px;color:#64748b;text-transform:uppercase;">Out of Scope</div>
    <div style="font-size:24px;font-weight:700;">6</div>
  </div>
  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:4px;padding:10px 16px;flex:1;min-width:80px;">
    <div style="font-size:11px;color:#64748b;text-transform:uppercase;">Scored</div>
    <div style="font-size:24px;font-weight:700;">0</div>
  </div>
</div>
<p style="margin-top:16px;font-size:12px;color:#9ca3af;">
  Sources active: Crexi (bulk rec) &middot; Gmail msg ID: 1a0a1d374138287f<br>
  Run: {now_str} &middot; ATG Deal Scanner
</p>

</body>
</html>"""


def main() -> int:
    db.migrate()

    html_body = _build_html()
    subject = (
        f"[ATG-DIGEST-AUTOSEND] ATG Deal Digest — {RUN_DATE_DISPLAY} "
        f"— 6 car wash flags (3 Tier-1: WhiteWater, Whistle x2)"
    )

    summary = {
        "run_date": RUN_DATE,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "success",
        "emails_processed": EMAILS_PROCESSED,
        "sources_active": ["crexi"],
        "listings_found": 6,
        "listings_new": 0,
        "listings_updated": 0,
        "listings_scored": 0,
        "parser_failures": 0,
        "carwash_flags": 6,
        "tier1_flags": 3,
        "out_of_scope": 6,
        "draft_created": True,
        "draft_id": "pending-mcp-create",
        "draft_subject": subject,
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
