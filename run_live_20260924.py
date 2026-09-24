"""Live scanner run for 2026-09-24 — feeds today's Gmail MCP data into the pipeline.

Usage:  uv run python run_live_20260924.py
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
log = get_logger("run_live_20260924")

# ── Emails fetched from Gmail MCP 2026-09-24 ─────────────────────────────
# One Crexi "personally recommended" digest email (12 property cards).
# Subject does not match any saved-search keyword so defaults to msa_commercial.
# Cards do not include asking prices (cap rates only) → body parser will skip
# most properties for lack of price+sf. Any that do extract will be scored.

CREXI_BODY = """\
Properties on Crexi personally recommended for you. Update your Saved Searches to improve your recommendations.

1701 St. Julian Place
1701 St. Julian Place, Columbia, SC 29204
1701 St. Julian Place, Columbia, SC 29204-2418

Whistle Express Car Wash | Denton, TX
1900 W University Dr, Denton, TX 76201
Retail | 5.75% CAP | 5,565 SqFt

Shell
109 S Main St, Big Pine, CA 93513
Retail | 6.75% CAP | 5,737 SF

Sonic
6949 Maynardville Pike, Knoxville, TN 37918
Retail | 5.20% CAP | 1,244 SqFt

Flex Wash Car Wash
1285 U.S. 31 N, Petoskey, MI 49770
Special Purpose | 6.25% CAP | 5,000 SqFt

101 Greystone Blvd
101 Greystone Blvd, Columbia, SC 29210
Office | 242,444 SqFt

Pinnacle Gas | Miami | 22 Year Lease
3695 NW 167th St, Miami Gardens, FL 33056
Pinnacle Gas | Miami | 22 Year Lease

DEVELOPMENT PROJECT- FOREST RANCH
15456 Forest Ranch Way, Forest Ranch, CA 95942
Retail | 4,384 SqFt

Shell Station - Palmetto
1240 8th Ave W, Palmetto, FL 34221
Retail | 6.10% CAP | 16 Years Remaining On Lease | Heavy Traffic Corridor

Arco/AMPM | Citrus Heights, CA
7560 Sunrise Blvd, Citrus Heights, CA 95610
Retail | 5.75% CAP | 3,810 SqFt

Sale - 750 W Lake Mary Blvd
750 W LAKE MARY BLVD, SANFORD, FL 32773
Gas Station for Sale - Real Estate Included!

Lot 1-Arco AM/PM Gas Convenience Store & QSR Fully Approved
Lake Elsinore, CA 92530
Fully Approved Gas Station C-Store & QSR site CUP in hand
"""

EMAILS: list[dict] = [
    {
        "id": "1a0d0282531b3bd6",
        "thread_id": "1a0d0282531b3bd6",
        "sender": "emails@search.crexi.com",
        "subject": "12 New properties recommended for you",
        "received_at": "2026-09-23T21:24:43Z",
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

    # 24-hour look-back window: 2026-09-23 06:30 CT = 11:30 UTC
    since = datetime(2026, 9, 23, 11, 30, 0, tzinfo=timezone.utc)
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
