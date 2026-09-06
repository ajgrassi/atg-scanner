"""Live scanner run for 2026-09-06 — feeds today's Gmail MCP data into the pipeline.

Usage:  uv run python run_20260906.py
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
log = get_logger("run_20260906")

# ── Emails fetched from Gmail MCP 2026-09-06 ─────────────────────────────
# One Crexi email found: generic "12 New properties recommended" alert.
# Subject does not match any saved-search channel keyword.
# All listings are in SC/FL — will not pass msa_commercial (MO-only) filter.
EMAILS: list[dict] = [
    {
        "id": "1a073c0eb6f6e33c",
        "thread_id": "1a073c0eb6f6e33c",
        "sender": "emails@search.crexi.com",
        "subject": "12 New properties recommended for you",
        "received_at": "2026-09-05T22:46:54Z",
        "text_body": (
            "Properties on Crexi personally recommended for you.\n\n"
            "125 Park Place Court\n125 Park Pl Ct, Lexington, SC 29072\n"
            "Single Tenant Medical NNN Investment Offering | 4,715 SqFt\n\n"
            "229 Longtown Road\n229 Longtown Rd, Columbia, SC 29229\n"
            "9,873 SF class A medical office building located in NE Columbia\n\n"
            "2205 Decker Blvd\n2205 Decker Blvd, Columbia, SC 29205\n"
            "Retail | 11,800 SqFt\n\n"
            "7-Eleven | Tampa, FL\n702 S 50th St, Tampa, FL 33619\n"
            "5.00% CAP | Corp Abs. NNN\n\n"
            "950 Taylor St\n950 Taylor St, Columbia, SC 29201\n"
            "Office | 25,000 SqFt\n\n"
            "3038 McNaughton Drive\n3038 McNaughton Drive, Columbia, SC 29223\n"
            "For Sale or Lease | Office/Warehouse Flex Space with Storage Bldg\n\n"
            "St Andrews Executive Offices\n7193 St Andrews Rd, Columbia, SC 29212\n"
            "Office | 3,500 SqFt\n\n"
            "00 70 Highway\n00 70 Highway, Barnwell, SC 29812\n"
            "Office | 3,495 SqFt\n\n"
            "1225 B Avenue\n1225 B Avenue, West Columbia, SC 29169\n"
            "Office | 3,678 SqFt\n\n"
            "2136 Sunset Blvd\n2136 Sunset Blvd, West Columbia, SC 29169\n"
            "Retail | 35,000 SqFt\n\n"
            "Bush River Court\n1501 Bush River Rd, Columbia, SC 29210\n"
            "Retail | 2,125 SF\n\n"
            "3610 Beach Boulevard\n3610 Beach Boulevard, Jacksonville, FL 32207\n"
            "Brand New Chevron Station - 7.50% Cap Rate, 20-Year NNN Lease\n\n"
        ),
    },
]

DRAFT_OUT = Path("data/draft_request.json")


class PreloadedGmailClient:
    def __init__(self, messages: list[EmailMessage]) -> None:
        self._messages = messages
        self.draft_id_created: str | None = None

    def search(self, query: str, max_results: int = 100) -> list[EmailMessage]:
        return self._messages

    def fetch_attachments(self, message_id: str, save_dir: str) -> list:
        return []

    def create_draft(self, draft: DraftRequest) -> str:
        DRAFT_OUT.write_text(
            json.dumps({
                "to": draft.to,
                "subject": draft.subject,
                "html_body": draft.html_body,
                "text_body": draft.text_body,
            }, indent=2),
            encoding="utf-8",
        )
        self.draft_id_created = "pending-mcp"
        return "pending-mcp"


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
    DRAFT_OUT.unlink(missing_ok=True)

    messages = build_messages()
    client = PreloadedGmailClient(messages)

    # 24h window: yesterday 6:30 AM Central
    since = datetime(2026, 9, 5, 11, 30, 0, tzinfo=timezone.utc)  # 6:30 AM CT = 11:30 UTC
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

    if DRAFT_OUT.exists():
        d = json.loads(DRAFT_OUT.read_text(encoding="utf-8"))
        print("\n--- DRAFT SUBJECT ---")
        print(d["subject"])
    else:
        print("\nNo draft created (no qualifying listings today).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
