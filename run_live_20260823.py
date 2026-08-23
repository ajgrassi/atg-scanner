"""Live scanner run for 2026-08-23 — daily 6:30am CT routine.

Emails found today (last 24h, Aug 22 11:30 UTC → Aug 23 11:30 UTC):
  1. emails@search.crexi.com — "12 New properties recommended for you" (Aug 22 22:44 UTC)
     → Parser routes by subject → no saved-search keyword match → defaults to msa_commercial
     → Body parser finds first address (100 Jimmy Love Ln, Columbia SC) → no price/SF → 0 listings extracted
     → Pipeline result: 0 qualifying listings

Notable listing manually spotted in recommendation email (pipeline limitation — bulk format):
  - Whistle Express, 7801 Sheridan Rd, White Hall AR 71602
    5.50% CAP | 4,525 SqFt | Special Purpose
    Tier-1 brand — needs click-through for price, lease term, structural gate data

Usage:  uv run python run_live_20260823.py
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
log = get_logger("run_live_20260823")

# ── Emails fetched from Gmail MCP (24h window: Aug 22 → Aug 23)
EMAILS: list[dict] = [
    {
        "id": "1a02ba5c6cc16c9c",
        "thread_id": "1a02ba5c6cc16c9c",
        "sender": "emails@search.crexi.com",
        "subject": "12 New properties recommended for you",
        "received_at": "2026-08-22T22:44:37Z",
        # Clean plain-text extraction of the recommendation email body.
        # This is a bulk "12 recommendations" email — not a per-listing saved-search alert.
        # Parser will find first address (100 Jimmy Love Ln) but no price/SF → 0 listings.
        "text_body": (
            "Properties on Crexi personally recommended for you.\n\n"
            "100 Jimmy Love Ln, Columbia, SC 29212\nMedical Space for sale or lease\n\n"
            "112 Arrowwood Rd, Columbia, SC 29210\n"
            "A Flexible Commercial Opportunity in Columbia's Proven St. Andrews Corridor\n\n"
            "1821 Augusta Road, West Columbia, SC 29169\n"
            "High-Visibility Augusta Road offering immediate Use and Long Term Value\n\n"
            "7116 Fire Lane Rd, Columbia, SC 29223\n3,782 SF Office/Renovated in 2020/Prime location\n\n"
            "7451 Irmo Drive, Columbia, SC 29212\n\n"
            "811 Sunset Boulevard, West Columbia, SC 29169\nOffice | 4,343 SF\n\n"
            "999 Harbor Drive, West Columbia, SC 29169\n\n"
            "12775 Palm Dr, Desert Hot Springs, CA 92240\nHigh Volume Gas & Store Sales!\n\n"
            "110 N Lake Dr, Lexington, SC 29072\n"
            "Mixed Use | Well-positioned opportunity near Lexington's Expansive Growth downtown area\n\n"
            "Whistle Express\n7801 Sheridan Rd, White Hall, AR 71602\n"
            "Special Purpose | 5.50% CAP | 4,525 SqFt\n\n"
            "Shell\n301 Los Angeles Ave, Moorpark, CA 93021\nat Mission Bell Plaza\n\n"
            "SAN CARLOS SHELL SERVICE STATION\n500 El Camino Real, San Carlos, CA 94070\n"
            "Retail | 16,700 SqFt\n"
        ),
    },
]

# ── Manually spotted car wash listing in recommendation email ──────────────
ATTENTION_ITEMS = [
    {
        "title": "Whistle Express Car Wash",
        "address": "7801 Sheridan Rd, White Hall, AR 71602",
        "channel": "car_wash_nnn",
        "source": "Crexi recommendation email (emails@search.crexi.com)",
        "data_in_email": "5.50% CAP | 4,525 SqFt | Special Purpose",
        "brand_tier": "Tier-1 (Whistle Express)",
        "note": (
            "Pipeline could not extract — bulk recommendation email format (no per-listing price/lease data). "
            "CAP at 5.50% is below ATG 6% target; tier-1 brand may justify. "
            "Click through to Crexi for: asking price, lease type, term remaining, "
            "roof responsibility, and bonus dep eligibility before scoring."
        ),
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


def _build_attention_html(items: list[dict], pipeline_summary: dict) -> str:
    rows = ""
    for item in items:
        rows += f"""
        <tr style="border-bottom:1px solid #e5e7eb;">
          <td style="padding:12px 8px;font-weight:600;color:#1e3a5f;">{item['title']}</td>
          <td style="padding:12px 8px;">{item['address']}</td>
          <td style="padding:12px 8px;color:#d97706;font-weight:600;">{item['brand_tier']}</td>
          <td style="padding:12px 8px;">{item['data_in_email']}</td>
          <td style="padding:12px 8px;font-size:12px;color:#6b7280;">{item['note']}</td>
        </tr>"""

    stats = pipeline_summary
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body{{font-family:Arial,sans-serif;font-size:14px;color:#111;max-width:900px;margin:0 auto;padding:16px}}
  h2{{color:#1e3a5f;border-bottom:2px solid #1e3a5f;padding-bottom:6px}}
  h3{{color:#374151;margin-top:24px}}
  table{{width:100%;border-collapse:collapse;margin-top:8px}}
  th{{background:#1e3a5f;color:#fff;padding:10px 8px;text-align:left;font-size:13px}}
  .stat-box{{background:#f3f4f6;border-radius:6px;padding:12px 16px;margin:8px 0;display:inline-block;min-width:160px}}
  .stat-label{{font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:.5px}}
  .stat-value{{font-size:22px;font-weight:700;color:#1e3a5f}}
  .note-box{{background:#fef3c7;border-left:4px solid #d97706;padding:10px 14px;margin:12px 0;border-radius:0 4px 4px 0}}
</style></head>
<body>
<h2>ATG Deal Scanner — Sun, Aug 23 — 0 new, 1 flagged for review</h2>

<div class="note-box">
  <strong>Pipeline result: 0 qualifying listings.</strong>
  Today's email from Crexi is a bulk "12 recommendations" format — not a per-listing saved-search alert.
  The parser extracts from the first address only and found no price/SF data.
  One tier-1 car wash listing was manually identified and flagged below — click through for details.
</div>

<h3>Flagged for Manual Review (1)</h3>
<table>
  <tr>
    <th>Property</th><th>Address</th><th>Brand</th><th>Available Data</th><th>Notes</th>
  </tr>
  {rows}
</table>

<h3>Scan Stats</h3>
<div>
  <div class="stat-box"><div class="stat-label">Emails Processed</div><div class="stat-value">{stats.get('emails_processed',1)}</div></div>
  <div class="stat-box"><div class="stat-label">Listings Found</div><div class="stat-value">{stats.get('listings_found',0)}</div></div>
  <div class="stat-box"><div class="stat-label">New</div><div class="stat-value">{stats.get('listings_new',0)}</div></div>
  <div class="stat-box"><div class="stat-label">Parser Failures</div><div class="stat-value">{len(stats.get('parser_failures',[]))}</div></div>
</div>
<p style="margin-top:16px;font-size:12px;color:#9ca3af;">
  Sources active: {', '.join(stats.get('sources_active',[])) or 'none'}<br>
  Sources failed: {', '.join(stats.get('sources_failed',[])) or 'none'}<br>
  Run: {stats.get('started_at','')[:19]} UTC
</p>
</body></html>"""


def main() -> int:
    db.migrate()
    draft_out = Path("data/draft_request.json")
    draft_out.unlink(missing_ok=True)

    messages = build_messages()
    client = PreloadedGmailClient(messages, draft_out)
    since = datetime(2026, 8, 22, 11, 30, 0, tzinfo=timezone.utc)

    summary = pipeline.run(
        client=client,
        since=since,
        dry_run=True,   # we'll create the draft ourselves below
        max_messages=50,
    )

    log_path = Path("data/run_log.json")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    if log_path.exists():
        try:
            rows = json.loads(log_path.read_text(encoding="utf-8"))
        except Exception:
            rows = []

    # Since we have a flagged item, create an attention draft even with 0 formal results.
    html_body = _build_attention_html(ATTENTION_ITEMS, summary)
    draft_payload = {
        "to": ["agrassi@ybpsrv.com"],
        "subject": "[ATG-DIGEST-AUTOSEND] ATG Deal Digest — Sun, Aug 23 — 0 new, 1 flagged",
        "html_body": html_body,
    }
    draft_out.write_text(json.dumps(draft_payload, indent=2), encoding="utf-8")
    summary["draft_created"] = True
    summary["draft_id"] = "pending-mcp-create"
    summary["flagged_for_review"] = len(ATTENTION_ITEMS)

    rows.append(summary)
    log_path.write_text(json.dumps(rows[-365:], indent=2, default=str), encoding="utf-8")

    print(json.dumps({k: v for k, v in summary.items() if k != "gmail_query"}, indent=2, default=str))
    print("\n--- DRAFT SUBJECT ---")
    print(draft_payload["subject"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
