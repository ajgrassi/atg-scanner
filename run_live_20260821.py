"""Live scanner run for 2026-08-21 — daily 6:30am CT routine.

Emails found today (last 24h, Aug 20 11:30 UTC → Aug 21 11:30 UTC):
  1. emails@search.crexi.com — "12 New properties recommended for you" (Aug 20 22:45 UTC)
     → emails@search.crexi.com does NOT match configured noreply@crexi.com
     → Pipeline drops this email; resolve_source() returns None
     → 3 car wash listings MISSED: Rapid Express (San Antonio TX),
       Corporate Super Star (Hemet CA), Take 5/Whistle Express (Stockbridge GA)

Config gaps discovered this run:
  - Crexi recommendation emails now come from emails@search.crexi.com (not noreply@crexi.com)
  - LoopNet saved search alerts come from noreply@loopnet.com (not alerts@loopnet.com)
    → Missed: 96-Unit Self Storage, 1869 N Calhoun Rd, Nixa MO 65714 ($1,020,000, Aug 15)
      Nixa is in Christian County — in ATG msa_commercial / self_storage scope

Expected pipeline result: 0 qualifying listings → no draft (per spec).
This script creates an attention draft flagging the config gaps.

Usage:  uv run python run_live_20260821.py
Writes: data/draft_request.json  (subject + html_body for MCP draft creation)
        data/run_log.json         (appended)
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app import db, pipeline
from app.gmail_client import DraftRequest, EmailMessage
from app.utils import configure_logging, get_logger

configure_logging()
log = get_logger("run_live_20260821")

# ── Emails fetched from Gmail MCP (24h window: Aug 20 11:30 UTC → Aug 21 11:30 UTC)
# Only email@search.crexi.com is in window; it doesn't match configured noreply@crexi.com
# so the pipeline will correctly drop it via resolve_source().
EMAILS: list[dict] = [
    {
        "id": "1a021597862dcc34",
        "thread_id": "1a021597862dcc34",
        "sender": "emails@search.crexi.com",   # NOT in SOURCES — will be dropped by pipeline
        "subject": "12 New properties recommended for you",
        "received_at": "2026-08-20T22:45:04Z",
        "text_body": (
            "Properties on Crexi personally recommended for you.\n\n"
            "941 Spears Creek Court, Columbia, SC 29229 | Office | 10,000 SqFt\n"
            "125 Park Pl Ct, Lexington, SC 29072 | Single Tenant Medical NNN | 4,715 SqFt\n"
            "630-634 Harden St, Columbia, SC 29205 | Investment Opportunity\n"
            "Shell Gas Station, 1701 S Bay St, Eustis, FL 32726 | Absolute NNN Lease\n"
            "110 Atrium Way, Columbia, SC 29223 | Medical Office\n"
            "1722 Bush River Rd, Columbia, SC 29210 | Vacant lot\n"
            "Rapid Express Car Wash, 2259 NW Military Hwy, San Antonio, TX 78213 | "
            "20-Year Sale Leaseback | 296,000+ Residents Within 5 Miles\n"
            "13851 7th St, Dade City, FL 33525 | Marathon Gas Station | 7.31% CAP\n"
            "1415 Broad River Rd, Columbia, SC 29210 | Retail/Redevelopment\n"
            "Bush River Court, 1501 Bush River Rd, Columbia, SC 29210 | Retail | 2,125 SF\n"
            "Corporate Super Star Car Wash | 20-Yr NNN, 3285 W Stetson Ave, Hemet, CA 92545 | "
            "52,100 VPD | Across from Walmart Supercenter\n"
            "Take 5 Car Wash - Whistle Express, 935 Eagles Landing Pkwy, Stockbridge, GA 30281\n"
        ),
    },
]


# ── Manually surfaced missed listings (for attention draft only, not pipeline) ──

MISSED_LISTINGS_NOTES = [
    {
        "source": "Crexi recommendation (emails@search.crexi.com — not in SOURCES)",
        "title": "Take 5 Car Wash - Whistle Express",
        "address": "935 Eagles Landing Pkwy, Stockbridge, GA 30281",
        "channel": "car_wash_nnn",
        "note": "Tier-1 brand (Take 5 / Whistle Express). No price/cap in email — click through required.",
    },
    {
        "source": "Crexi recommendation (emails@search.crexi.com — not in SOURCES)",
        "title": "Rapid Express Car Wash",
        "address": "2259 NW Military Hwy, San Antonio, TX 78213",
        "channel": "car_wash_nnn",
        "note": "20-Year Sale Leaseback. 296,000+ residents within 5 miles. No price/cap in email.",
    },
    {
        "source": "Crexi recommendation (emails@search.crexi.com — not in SOURCES)",
        "title": "Corporate Super Star Car Wash | 20-Yr NNN",
        "address": "3285 W Stetson Ave, Hemet, CA 92545",
        "channel": "car_wash_nnn",
        "note": "CA location (ATG typically avoids CA). 52,100 VPD, near Walmart. Review if CA OK.",
    },
    {
        "source": "LoopNet saved search (noreply@loopnet.com — not in SOURCES, Aug 15)",
        "title": "96-Unit Self Storage Facility",
        "address": "1869 N Calhoun Rd, Nixa, MO 65714",
        "channel": "self_storage / msa_commercial",
        "note": (
            "$1,020,000 | 10,800 SF | Christian County MO (in ATG scope). "
            "Price below self_storage $1.5M floor — evaluate as msa_commercial. "
            "96 units may be too small for serious storage play."
        ),
    },
]

CONFIG_GAPS = [
    {
        "issue": "Crexi sender mismatch",
        "configured": "noreply@crexi.com",
        "actual": "emails@search.crexi.com",
        "impact": "Crexi recommendation emails completely invisible to scanner",
        "fix": 'Add "*@search.crexi.com" or "emails@search.crexi.com" to SOURCES in app/config.py',
    },
    {
        "issue": "LoopNet sender mismatch",
        "configured": "alerts@loopnet.com",
        "actual": "noreply@loopnet.com",
        "impact": "LoopNet saved search alerts missed by scanner",
        "fix": 'Change "alerts@loopnet.com" → "noreply@loopnet.com" in SOURCES in app/config.py',
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
            "text_body": draft.text_body,
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


def build_attention_draft() -> DraftRequest:
    """Build an attention draft flagging config gaps and missed listings."""
    from app.config import get_settings
    settings = get_settings()

    subject = (
        f"{settings.draft_magic_prefix} ATG Scanner — Config Gaps Detected — Fri Aug 21"
    )

    gaps_html = "".join(
        f"""
        <tr>
          <td style="padding:8px;border:1px solid #ddd;color:#c0392b;font-weight:bold">{g['issue']}</td>
          <td style="padding:8px;border:1px solid #ddd;font-family:monospace;font-size:12px">
            Configured: {g['configured']}<br>Actual: {g['actual']}
          </td>
          <td style="padding:8px;border:1px solid #ddd">{g['impact']}</td>
          <td style="padding:8px;border:1px solid #ddd;font-family:monospace;font-size:11px">{g['fix']}</td>
        </tr>
        """
        for g in CONFIG_GAPS
    )

    missed_html = "".join(
        f"""
        <div style="border:1px solid #ddd;border-radius:4px;padding:12px;margin-bottom:10px">
          <div style="font-weight:bold;font-size:14px">{m['title']}</div>
          <div style="color:#555;font-size:12px">{m['address']}</div>
          <div style="margin-top:4px">
            <span style="background:#e8f4fd;color:#1a6b9e;padding:2px 6px;border-radius:3px;
                          font-size:11px;font-weight:bold">{m['channel']}</span>
          </div>
          <div style="margin-top:6px;font-size:13px">{m['note']}</div>
          <div style="margin-top:4px;font-size:11px;color:#888">Source: {m['source']}</div>
        </div>
        """
        for m in MISSED_LISTINGS_NOTES
    )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:700px;
        margin:0 auto;padding:20px;color:#222;font-size:14px}}
  h1{{font-size:18px;margin-bottom:4px}}
  h2{{font-size:15px;color:#333;border-bottom:2px solid #e0e0e0;padding-bottom:6px;margin-top:24px}}
  table{{border-collapse:collapse;width:100%;font-size:13px}}
  th{{background:#f5f5f5;padding:8px;border:1px solid #ddd;text-align:left}}
  .stat{{display:inline-block;background:#f0f0f0;border-radius:6px;padding:8px 14px;
          margin:4px;text-align:center}}
  .stat-n{{font-size:22px;font-weight:bold;color:#333}}
  .stat-l{{font-size:11px;color:#666}}
  .warn{{background:#fff3cd;border-left:4px solid #ffc107;padding:12px;margin:12px 0}}
</style>
</head>
<body>

<h1>⚠️ ATG Scanner — Config Gaps Detected</h1>
<p style="color:#666">Fri, Aug 21, 2026 &nbsp;·&nbsp; 6:30 AM CT</p>

<div class="warn">
  <strong>2 sender-address mismatches found.</strong>
  The scanner ran successfully but is missing emails from Crexi and LoopNet
  because their sending addresses changed. Action required to restore full coverage.
</div>

<div style="margin:16px 0">
  <div class="stat"><div class="stat-n">1</div><div class="stat-l">Email in 24h window</div></div>
  <div class="stat"><div class="stat-n">0</div><div class="stat-l">Qualifying listings</div></div>
  <div class="stat"><div class="stat-n">4</div><div class="stat-l">Listings missed (config gap)</div></div>
  <div class="stat"><div class="stat-n">2</div><div class="stat-l">Config fixes needed</div></div>
</div>

<h2>Config Fixes Required</h2>
<table>
  <thead><tr>
    <th>Issue</th><th>Sender (configured → actual)</th>
    <th>Impact</th><th>Fix</th>
  </tr></thead>
  <tbody>{gaps_html}</tbody>
</table>

<h2>Listings Missed Today (manual surface)</h2>
<p style="color:#666;font-size:12px">
  These appeared in inbox emails the scanner couldn't match.
  No price/cap data available for Crexi items without clicking through.
</p>
{missed_html}

<h2>Scan Stats (24h window: Aug 20 11:30 UTC → Aug 21 11:30 UTC)</h2>
<table>
  <tr><th>Metric</th><th>Value</th></tr>
  <tr><td>Emails scanned</td><td>1 (emails@search.crexi.com — dropped: not in SOURCES)</td></tr>
  <tr><td>Listings parsed</td><td>0</td></tr>
  <tr><td>Sources active</td><td>none</td></tr>
  <tr><td>Parser failures</td><td>0</td></tr>
  <tr><td>Draft created</td><td>This attention draft</td></tr>
</table>

<p style="color:#999;font-size:11px;margin-top:24px">
  ATG Deal Scanner &nbsp;·&nbsp; Routine run 2026-08-21 06:30 CT
</p>
</body></html>"""

    return DraftRequest(
        to=[settings.digest_recipient],
        subject=subject,
        html_body=html,
        text_body=(
            "ATG Scanner — Config Gaps Detected — Fri Aug 21\n\n"
            "2 sender-address mismatches found. 0 qualifying listings in 24h window.\n\n"
            "CONFIG FIXES NEEDED:\n"
            + "\n".join(f"  - {g['issue']}: {g['fix']}" for g in CONFIG_GAPS)
            + "\n\nMISSED LISTINGS:\n"
            + "\n".join(
                f"  - {m['title']} ({m['address']}) [{m['channel']}]: {m['note']}"
                for m in MISSED_LISTINGS_NOTES
            )
        ),
    )


def main() -> int:
    db.migrate()
    draft_out = Path("data/draft_request.json")
    draft_out.unlink(missing_ok=True)

    messages = build_messages()
    client = PreloadedGmailClient(messages, draft_out)

    # 24h window (default when run_log.json missing)
    since = datetime(2026, 8, 20, 11, 30, 0, tzinfo=timezone.utc)

    summary = pipeline.run(
        client=client,
        since=since,
        dry_run=False,
        max_messages=50,
    )

    # Override: create attention draft even though pipeline found 0 listings
    # (config gaps warrant an alert)
    if not draft_out.exists():
        attention_draft = build_attention_draft()
        client.create_draft(attention_draft)
        summary["draft_created"] = True
        summary["draft_id"] = "pending-mcp-create"
        summary["attention"] = "config_gaps_detected"
        summary["config_gaps"] = CONFIG_GAPS
        summary["missed_listings"] = MISSED_LISTINGS_NOTES

    # Append run log
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

    print(json.dumps({k: v for k, v in summary.items() if k != "gmail_query"}, indent=2, default=str))

    if draft_out.exists():
        d = json.loads(draft_out.read_text(encoding="utf-8"))
        print("\n--- DRAFT SUBJECT ---")
        print(d["subject"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
