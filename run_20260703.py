"""Daily runner for 2026-07-03 — July 4th holiday week, quiet day.

Gmail MCP searched for broker emails newer_than:1d (since ~2026-07-02 11:30 UTC).
Result: 0 matching threads. The July 1 Sands IG email (Westside RV Park, $640K)
is outside the 24h default window and would also fail self_storage price gate
($640K < $1.5M floor) regardless.

Usage:  uv run python run_20260703.py
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
log = get_logger("run_20260703")

# Gmail MCP search (newer_than:1d from 2026-07-03 06:30 CT = after 2026-07-02 11:30 UTC):
# 0 broker emails returned. Holiday week — no broker blasts.
EMAILS: list[dict] = []


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


def main() -> int:
    db.migrate()
    draft_out = Path("data/draft_request.json")
    draft_out.unlink(missing_ok=True)

    messages = []  # 0 broker emails in 24h window
    client = PreloadedGmailClient(messages, draft_out)

    # Window: last 24h from 2026-07-03 06:30 Central = 11:30 UTC
    since = datetime(2026, 7, 2, 11, 30, 0, tzinfo=timezone.utc)
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
        print("\nNo draft created — quiet day, 0 broker emails in last 24h.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
