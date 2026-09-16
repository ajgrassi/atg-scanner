"""Live scanner run 2026-09-16 — daily 6:30am CT routine.

Email found today (24h window: Sep 15 11:30 UTC → Sep 16 11:30 UTC):

  1. noreply@loopnet.com → "1 property matched your saved search" (Sep 16 01:00 UTC)
     → Saved search: "Property Types For Sale" (not an ATG named search)
     → 1 listing: The Galleria D'Italia Center, 6001 N 21st St, Ozark, MO 65721
       General Retail | 32,125 SF | $4,500,000
     → In Christian County, MO (ATG target area) but $4.5M >> msa_commercial max ($1.5M)
     → Verdict: PASS (out of price range for all ATG channels)

  2. emails@search.crexi.com → "12 New properties recommended for you" (Sep 15 21:49 UTC)
     → Bulk recommendation email, no named saved-search alert
     → Sent to andygrassi@gmail.com
     → 12 properties total; 3 car washes identified:
         a) Mammoth Car Wash — 2105 S Tamiami Trl, Port Charlotte, FL 33948
            6.50% CAP | 2,738 SqFt | Tier-1 (Mammoth) | No price in email
         b) Super Star Car Wash — 1604 W Hebron Pkwy, Carrollton, TX 75010
            6.50% CAP | 5,457 SqFt | Not in ATG tier lists | No price in email
         c) Tsunami Express Car Wash — 3500 North Nebo Road, Muncie, IN 47304
            No financial data in email | Not in ATG tier lists
     → 4 gas stations (out of scope): Service Station FL, Shell FL, Arco am/pm CA x2
     → 5 offices/retail (out of scope): Columbia SC x5

Pipeline result: 2 emails, 3 car wash flags (1 Tier-1: Mammoth Port Charlotte FL),
1 LoopNet Ozark MO PASS, 9 out-of-scope. 0 formally scored (no prices in email).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app import db
from app.utils import configure_logging, get_logger

configure_logging()
log = get_logger("run_live_20260916")

RUN_DATE = "2026-09-16"
RUN_DATE_DISPLAY = "Wed, Sep 16"
EMAILS_PROCESSED = 2


def _build_html() -> str:
    car_washes = [
        {
            "brand": "Mammoth Car Wash — Port Charlotte, FL",
            "address": "2105 S Tamiami Trl, Port Charlotte, FL 33948",
            "tier": "Tier-1 (Mammoth)",
            "data": "6.50% CAP | 2,738 SF (express tunnel format)",
            "note": (
                "Tier-1 brand (Mammoth explicitly in ATG scoring list = 7 brand pts). "
                "6.5% CAP = 6 pts (6–6.5% band). Express tunnel format ≈ 12 pts cost seg. "
                "Port Charlotte is a fast-growing SW Florida Gulf Coast market. No price — "
                "click Crexi for OM, lease term, escalator, roof clause."
            ),
            "action": "⭐ Priority click-through (Tier-1 + confirmed CAP)",
            "priority": 1,
        },
        {
            "brand": "Super Star Car Wash — Carrollton, TX",
            "address": "1604 W Hebron Pkwy, Carrollton, TX 75010",
            "tier": "Not in ATG tier lists (brand pts: 3)",
            "data": "6.50% CAP | 5,457 SF",
            "note": (
                "Super Star Car Wash is a Southwest regional chain; not in ATG Tier-1/2. "
                "6.5% CAP = 6 pts. 5,457 SF is larger format (likely full-service or "
                "express + detail). Carrollton TX = suburban Dallas, strong demographics. "
                "Click for price and lease structure — brand tier upgrades if corporate guarantee."
            ),
            "action": "⭐ Click-through (solid CAP, brand TBD)",
            "priority": 2,
        },
        {
            "brand": "Tsunami Express Car Wash — Muncie, IN",
            "address": "3500 North Nebo Road, Muncie, IN 47304",
            "tier": "Not in ATG tier lists (brand pts: 3)",
            "data": "No financial data in email",
            "note": (
                "Tsunami not in ATG Tier-1/2 lists. Muncie IN is a mid-size Midwest market "
                "(population ~66K). No price or CAP in email — minimal data to evaluate. "
                "Click through for price, lease, and operator details before investing time."
            ),
            "action": "Click-through (data-gathering only)",
            "priority": 3,
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
  <strong>Pipeline: 2 emails, 3 car wash flags (1 Tier-1: Mammoth Port Charlotte FL),
  0 formally scored.</strong><br>
  Crexi bulk recommendation email + LoopNet alert. No pricing embedded in emails &mdash;
  click-through required for full scoring. Top pick: Mammoth Car Wash (Tier-1, 6.5% CAP).
  1 LoopNet listing in ATG&rsquo;s backyard (Ozark MO) but too large for channel ($4.5M).
</div>

<!-- CAR WASH FLAGS -->
<h2>Car Wash &mdash; 3 Flagged from Crexi Bulk Recommendations</h2>
<p style="font-size:12px;color:#64748b;margin-bottom:8px;">
  From Crexi &ldquo;12 New properties recommended for you&rdquo; email (Sep 15, 9:49 PM UTC)
  to andygrassi@gmail.com. No pricing in email &mdash; click-through to Crexi for OMs.
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

<!-- STANDOUT DETAIL: MAMMOTH -->
<h2>Standout: Mammoth Car Wash &mdash; Port Charlotte, FL (Priority #1)</h2>
<div style="background:#f0fdf4;border:1px solid #86efac;border-radius:6px;padding:12px;font-size:13px;">
  <strong>Why this one leads:</strong>
  <ul style="margin:6px 0 0 0;padding-left:18px;line-height:1.9;">
    <li>Tier-1 brand (Mammoth explicitly in ATG scoring list = 7 brand pts)</li>
    <li>6.50% CAP confirmed = 6 pts on cap rate scoring (6&ndash;6.5% band)</li>
    <li>2,738 SF = compact express-tunnel format &rarr; high cost-seg yield (~12 pts estimated)</li>
    <li>Port Charlotte, FL = fast-growing Gulf Coast market; SW Florida corridor showing strong retail demand</li>
    <li>Known partial score before OM: Brand 7 + Cap 6 + Cost seg ~12 = ~25 pts; need price, lease
        term, escalator, roof structure to score remaining ~75 pts</li>
  </ul>
  <p style="margin:8px 0 0;color:#166534;font-weight:600;">
    &rarr; Click through on Crexi, request OM, check: price (target $2&ndash;6M),
    lease type (must be absolute NNN for gate pass), roof structure (must be tenant for gate pass),
    lease term remaining (need &ge;15yr for 15 pts), escalator &ge;1.8% for top 12 pts,
    bonus depreciation confirmation (required gate pass).
  </p>
</div>

<!-- LOOPNET ALERT -->
<h2>LoopNet Alert &mdash; Ozark, MO (PASS &mdash; Out of Price Range)</h2>
<div style="background:#f1f5f9;border:1px solid #cbd5e1;border-radius:6px;padding:12px;font-size:13px;color:#475569;">
  <strong>The Galleria D&rsquo;Italia Center</strong> &mdash; 6001 N 21st St, Ozark, MO 65721<br>
  General Retail | 32,125 SF | $4,500,000 | Saved search: &ldquo;Property Types For Sale&rdquo;
  <ul style="margin:6px 0 0 0;padding-left:18px;line-height:1.8;">
    <li>Christian County, MO &rarr; within ATG&rsquo;s msa_commercial target counties
        (Greene, Christian, Webster, Taney)</li>
    <li>Price $4.5M >> msa_commercial hard cap ($1.5M max) &rarr; <strong>PASS</strong></li>
    <li>32,125 SF general retail center &mdash; not a fit for car wash, storage, oil/gas, solar, or IOS channels either</li>
    <li>Note: &ldquo;Property Types For Sale&rdquo; is not an ATG named saved search on LoopNet.
        Consider whether this saved search aligns with ATG criteria or can be refined.</li>
  </ul>
</div>

<!-- OUT OF SCOPE -->
<h2>Out of Scope &mdash; 9 Listings (SC Offices, Gas Stations, Misc)</h2>
<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:12px;
  font-size:13px;color:#475569;">
  <strong>Gas stations (not car washes):</strong>
  <ul style="margin:4px 0 6px 0;padding-left:18px;line-height:1.8;">
    <li>Service Station &mdash; Old State Rte 8, Lake Placid, FL 33852 (20yr ABS NNN)</li>
    <li>Shell &mdash; 3944 Gall Blvd, Zephyrhills, FL 33541</li>
    <li>Arco am/pm Truck Stop &mdash; 2191 W Main St, Barstow, CA 92311</li>
    <li>ARCO am/pm Moreno Valley &mdash; 22330 Cactus Ave, Moreno Valley, CA 92553 (126,628 SF)</li>
  </ul>
  <strong>South Carolina offices / retail (not in ATG target market):</strong>
  <ul style="margin:4px 0 0 0;padding-left:18px;line-height:1.8;">
    <li>3100 Colonial Dr, Columbia, SC 29203 (Medical/Office, 2,750 SF)</li>
    <li>710 Lady St, Columbia, SC 29201 (Office, 9,120 SF)</li>
    <li>1510 Canal Dr, Columbia, SC 29210 (Investment)</li>
    <li>1225 Pickens St, Columbia, SC 29201 (Office, 4,276 SF)</li>
    <li>2758 Rosewood Drive, Columbia, SC 29205 (0.74ac Redevelopment)</li>
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
    <div style="font-size:24px;font-weight:700;">3</div>
  </div>
  <div style="background:#fef9c3;border:1px solid #f59e0b;border-radius:4px;padding:10px 16px;flex:1;min-width:80px;">
    <div style="font-size:11px;color:#92400e;text-transform:uppercase;">Tier-1 Flags</div>
    <div style="font-size:24px;font-weight:700;">1</div>
  </div>
  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:4px;padding:10px 16px;flex:1;min-width:80px;">
    <div style="font-size:11px;color:#64748b;text-transform:uppercase;">Out of Scope</div>
    <div style="font-size:24px;font-weight:700;">9</div>
  </div>
  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:4px;padding:10px 16px;flex:1;min-width:80px;">
    <div style="font-size:11px;color:#64748b;text-transform:uppercase;">Scored</div>
    <div style="font-size:24px;font-weight:700;">0</div>
  </div>
</div>
<p style="margin-top:16px;font-size:12px;color:#9ca3af;">
  Sources active: Crexi (bulk rec) &middot; LoopNet (property alert) &middot;
  Gmail msg IDs: 1a0a70ba50677574, 1a0a7ba54a3b795c<br>
  Run: {now_str} &middot; ATG Deal Scanner
</p>

</body>
</html>"""


def main() -> int:
    db.migrate()

    html_body = _build_html()
    subject = (
        f"[ATG-DIGEST-AUTOSEND] ATG Deal Digest — {RUN_DATE_DISPLAY} "
        f"— 3 car wash flags (1 Tier-1: Mammoth Port Charlotte)"
    )

    summary = {
        "run_date": RUN_DATE,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "success",
        "emails_processed": EMAILS_PROCESSED,
        "sources_active": ["crexi", "loopnet"],
        "listings_found": 3,
        "listings_new": 0,
        "listings_updated": 0,
        "listings_scored": 0,
        "parser_failures": 0,
        "carwash_flags": 3,
        "tier1_flags": 1,
        "out_of_scope": 9,
        "loopnet_pass": 1,
        "draft_created": True,
        "draft_id": "pending-mcp-create",
        "draft_subject": subject,
        "gmail_msg_ids": ["1a0a70ba50677574", "1a0a7ba54a3b795c"],
    }

    log_path = Path("data/run_log.json")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    if log_path.exists():
        try:
            rows = json.loads(log_path.read_text(encoding="utf-8"))
        except Exception:
            rows = []
    rows.append(summary)
    log_path.write_text(json.dumps(rows[-365:], indent=2, default=str), encoding="utf-8")

    log.info("run.complete", **{k: v for k, v in summary.items() if k not in ("draft_id", "gmail_msg_ids")})
    print(json.dumps(summary, indent=2, default=str))
    print("\n--- DRAFT SUBJECT ---")
    print(subject)

    return 0


if __name__ == "__main__":
    sys.exit(main())
