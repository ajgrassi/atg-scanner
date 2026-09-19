"""Live scanner run for 2026-09-19 — feeds today's Gmail MCP data into the pipeline.

Usage:  uv run python run_live_20260919.py
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
log = get_logger("run_live_20260919")

# ── Emails fetched from Gmail MCP 2026-09-19 ─────────────────────────────
# Two broker emails received in the last 24 hours.

# LoopNet saved-search alert: 1 property in Springfield MO (Flex space)
LOOPNET_BODY = """\
LoopNet - Main saved search

1 new property matched your saved search for Property Types For Sale - 04/19/2026.

1447 S Enterprise Ave | Springfield, MO 65804 | Flex | For Sale
14,743 SF | Price Upon Request

View Listing
See Search Results
"""

# Crexi personal recommendations: 12 properties across multiple types/states
# Extracted from HTML-encoded tracking body
CREXI_BODY = """\
Properties on Crexi personally recommended for you.

710 Rabon Road
710 Rabon Rd, Columbia, SC 29203
Investment Opportunity: ±20,000 SF Class A Medical Office Building | Northeast Columbia
Property Type: Office
Building Size: 20,000 SF

Whistle Express
3205 Bemiss Road, Valdosta, GA 31605
Property Type: Car Wash
Lease Type: NNN

Whistle Express
200 Pacer Court Northwest, Corydon, IN 47112
Property Type: Car Wash
Lease Type: NNN

Mister Car Wash
3501 Northrise Drive, Las Cruces, NM 88011
Property Type: Car Wash
Rent Increases: 2% Annual Inc | Exceptional Store Performance
Lease Type: Absolute NNN
Roof: Tenant

6+/- Acres - Adjacent to 10057 Broad River Rd
10057 Broad River Road, Irmo, SC 29063
±6 Acres | Water & Sewer Available | High Visibility | Adjacent to 10057 Broad River Rd
Property Type: Land

Go Car Wash
1922 Empire Boulevard, Webster, NY 14580
Single Tenant Absolute NNN Car Wash
Property Type: Car Wash
Lease Type: Absolute NNN
Roof: Tenant

1200 Charleston Hwy
1200 Charleston Hwy, West Columbia, SC 29169
Retail | 15,000 SqFt
Property Type: Retail
Building Size: 15,000 SF

1101 Charleston Hwy
1101 Charleston Hwy, West Columbia, SC 29169
MIXED-USE | VALUE ADD INVESTMENT
Property Type: Mixed-Use

1627 Hwy 99
1627 CA-99, Gridley, CA 95948
Car Wash/Former Fuel Station on Hwy 99
Property Type: Car Wash

4860 Topaz | Las Vegas Carwash
4860 S Topaz St, Las Vegas, NV 89121
Actual 12.22% CAP RATE | 20.2% CAP UPSIDE
Property Type: Car Wash
Cap Rate: 12.22%

(7.1% Cap Rate) Amoco Station (20 Year Lease)
16135 U.S. 301, Dade City, FL 33523
Retail | 7.10% CAP | 3,408 SqFt
Cap Rate: 7.10%
Building Size: 3,408 SF
Lease Term: 20 Years

M Space
530 Lady St, Columbia, SC 29201
±6,000 SF Retail Space Available for Sale
Property Type: Retail
Building Size: 6,000 SF
"""

EMAILS: list[dict] = [
    {
        "id": "1a0b933af9cc2962",
        "thread_id": "1a0b933af9cc2962",
        "sender": "noreply@loopnet.com",
        "subject": "1 property matched your saved search",
        "received_at": "2026-09-19T10:26:06Z",
        "text_body": LOOPNET_BODY,
    },
    {
        "id": "1a0b66b24f268eb5",
        "thread_id": "1a0b66b24f268eb5",
        "sender": "emails@search.crexi.com",
        "subject": "12 New properties recommended for you",
        "received_at": "2026-09-18T21:27:45Z",
        "text_body": CREXI_BODY,
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


def main() -> int:
    db.migrate()
    draft_out = Path("data/draft_request.json")
    draft_out.unlink(missing_ok=True)

    messages = build_messages()
    client = PreloadedGmailClient(messages, draft_out)

    # 24-hour look-back window from 2026-09-18 06:30 CT (11:30 UTC)
    since = datetime(2026, 9, 18, 11, 30, 0, tzinfo=timezone.utc)
    summary = pipeline.run(
        client=client,
        since=since,
        dry_run=False,
        max_messages=50,
    )

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
    else:
        print("\nNo draft created (no qualifying listings).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
