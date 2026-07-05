"""Daily runner for 2026-07-05 — post-July 4th holiday weekend.

Gmail MCP searched for broker emails newer_than:1d (since ~2026-07-04 11:30 UTC).
Result: 1 matching thread — Hanley Investment Group "Happy Independence Day!"
holiday greeting (info@hanleyinvestment.com, thread 19f2dc1c8ede983f).
Email contains zero property listings — social media links + footer only.
Pipeline: 1 email processed, 0 listings extracted → quiet day, no draft.

Usage:  uv run python run_20260705.py
Writes: data/run_log.json  (appended)
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
log = get_logger("run_20260705")

# Gmail MCP search (newer_than:1d from 2026-07-05 06:30 CT = 11:30 UTC):
# 1 broker email returned — Hanley Investment "Happy Independence Day!" holiday
# greeting. No property listings in the body. Parser yields 0 listings.
EMAILS: list[dict] = [
    {
        "id": "19f2dc1c8ede983f",
        "thread_id": "19f2dc1c8ede983f",
        "sender": "info@hanleyinvestment.com",
        "subject": "Happy Independence Day!",
        "received_at": "2026-07-04T15:31:36Z",
        "text_body": (
            "Have a Wonderful and Safe 4th of July!\n\n"
            "View this email in your browser\n\n"
            "HIG Website | LinkedIn | Twitter | Facebook | Instagram\n\n"
            "This email was sent to agrassi@ybpsrv.com\n"
            "Hanley Lefko Investments, Inc. dba Hanley Investment Group\n"
            "3500 East Coast Highway, Corona del Mar, CA 92625, USA\n"
        ),
    },
]


class PreloadedGmailClient:
    def __init__(self, messages: list[EmailMessage], draft_out: Path):
        self._messages = messages
        self._draft_out = draft_out
        self.draft_created: str | None = None

    def search(self, query: str, max_results: int = 100) -> list[EmailMessage]:
        log.info("fake_gmail.search", count=len(self._messages))
        return self._messages

    def fetch_attachments(self, message_id: str, save_dir: str):
        return []

    def create_draft(self, draft: DraftRequest) -> str:
        payload = {
            "to": draft.to,
            "subject": draft.subject,
            "html_body": draft.html_body,
            "text_body": draft.text_body,
        }
        self._draft_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log.info("fake_gmail.draft_saved", path=str(self._draft_out))
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

    # Window: last 24h from 2026-07-05 06:30 Central = 11:30 UTC
    since = datetime(2026, 7, 4, 11, 30, 0, tzinfo=timezone.utc)
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
            rows = json.loads(log_path.read_text())
        except Exception:
            rows = []
    rows.append(summary)
    rows = rows[-365:]
    log_path.write_text(json.dumps(rows, indent=2, default=str))

    print(json.dumps({k: v for k, v in summary.items() if k != "gmail_query"}, indent=2, default=str))

    if draft_out.exists():
        draft = json.loads(draft_out.read_text())
        print("\n--- DRAFT SUBJECT ---")
        print(draft["subject"])
    else:
        print("\nNo draft created — quiet day: 1 broker email, 0 property listings (Hanley holiday greeting).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
