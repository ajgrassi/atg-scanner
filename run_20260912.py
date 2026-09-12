"""ATG Deal Scanner — 2026-09-12 live run.

Emails fetched from Gmail MCP at 6:30am CT. Two broker emails found:
  1. emails@search.crexi.com — "12 New properties recommended for you"
  2. noreply@loopnet.com    — "1 property matched your saved search"
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
log = get_logger("run_20260912")

# ── Emails fetched from Gmail MCP 2026-09-12 ─────────────────────────────
# Crexi personal-recommendations email — no saved-search routing keyword in
# subject; defaults to msa_commercial filter (which will gate most of these).
# Email body is table-based HTML converted to plaintext with minimal KV structure;
# the generic parser will attempt to extract addresses + prices.
CREXI_BODY = """Properties on Crexi personally recommended for you.

130 Whiteford Way, Lexington, SC 29072
Office | 6,640 SqFt

Big O Tires (Knoxville MSA)
121 North River Boulevard, Sevierville, TN 37876
8+ Years Remaining | NNN Lease

Jackson Ranch Mixed-Use HWY Commercial Development
Utica Ave, Kettleman, CA 93239
Retail

City Barbeque - Smyrna, TN
110 Sam Ridley Parkway East, Smyrna, TN 37167
Nashville MSA | City Barbeque | New Construction Ground Lease

7500 Asheville Hwy, Knoxville, TN 37924
Car Wash with Adjoining Valvoline | 5,770 SqFt

Waters Car Wash (Sale Leaseback)
3525 Millenia Blvd, Orlando, FL 32839
Waters Car Wash (Sale-Leaseback) | 100% Bonus Depreciation Eligible | Orlando, FL | 5.95% CAP

Outstanding BIZ Fee-Simple Partnership Opportunity!
21010 Geyserville Ave, Geyserville, CA 95441
Strong Fee-Simple Partnership Opportunity!

New Dutch Bros | Main Retail Corridor | 15-Yr NNN
1501 E. Stone Drive, Kingsport, TN 37664
Large Parcel | Near 239-bed hospital | Dutch Bros Coffee | NNN Lease | 15 Years

108 N Lake Dr, Lexington, SC 29072
Well-positioned office opportunity near downtown

Woodland Arco
16435 Co Rd 99, Woodland, CA 95695
Arco AMPM branded Gas Station with Car Wash

ANDERSON CA 96007
N/A, Anderson, CA 96007
Approved Fuel & Convenience Development Site

7-ELEVEN PORTFOLIO & ADVANCE AUTO PARTS | NNN LEASES
7770 Winter Garden Vineland Road, Windermere, FL 34786
7-ELEVEN PORTFOLIO & ADVANCE AUTO PARTS | FL LOCATIONS | NNN LEASES
"""

# LoopNet saved-search alert — saved-search name "Property Types For Sale -
# 04/19/2026" does not match any channel keyword, so defaults to msa_commercial.
# Listing: land parcel in Springfield, MO at $729,900.
LOOPNET_BODY = """1 new property matched your saved search for Property Types For Sale - 04/19/2026.

4.36 ACRES, HEAVY MANUFACTURING ZONING
1545 N Barnes Ave, Springfield, MO 65803
Land | For Sale
Lot Size: 4.36 AC
Asking Price: $729,900
"""

EMAILS: list[dict] = [
    {
        "id": "1a09261f58c34650",
        "thread_id": "1a09261f58c34650",
        "sender": "emails@search.crexi.com",
        "subject": "12 New properties recommended for you",
        "received_at": "2026-09-11T21:31:25Z",
        "text_body": CREXI_BODY,
    },
    {
        "id": "1a0923c8da3013dd",
        "thread_id": "1a0923c8da3013dd",
        "sender": "noreply@loopnet.com",
        "subject": "1 property matched your saved search for Property Types For Sale - 04/19/2026",
        "received_at": "2026-09-11T20:50:36Z",
        "text_body": LOOPNET_BODY,
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

    # Since this is a fresh DB, default to last-24h window.
    since = datetime(2026, 9, 11, 6, 30, 0, tzinfo=timezone.utc)
    summary = pipeline.run(
        client=client,
        since=since,
        dry_run=False,
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
