"""Daily runner for 2026-07-02 — feeds live Gmail data into the pipeline.

Email fetched live via Gmail MCP:
  1 message from kdeninno@sandsig.com — Westside RV Park, Sunrise Beach, MO

Usage:  uv run python run_20260702.py
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
log = get_logger("run_20260702")

# ── Pre-fetched email data from Gmail MCP (newer_than:1d, 2026-07-02 run) ──

EMAILS: list[dict] = [
    {
        "id": "19f1e709c48ab113",
        "thread_id": "19f1e709c48ab113",
        "sender": "kdeninno@sandsig.com",
        "subject": "RV Park | Lake of the Ozarks, MO | Seller Financing",
        "received_at": "2026-07-01T16:04:03Z",
        "text_body": (
            "Sands Investment Group is pleased to exclusively offer for sale Westside RV Park Asset "
            "located at 200 Northview Road in Sunrise Beach, Missouri.\n\n"
            "Westside RV Park - Sunrise Beach, MO\n\n"
            "PRICE\n\n$640,000\n\n"
            "CAP\nRATE\n\n6.84%\n\n"
            "ACRES\n\n8.29 Acres\n\n"
            "Investment Highlights\n\n"
            "Waterfront RV park located on Lake of the Ozarks, offering a scenic lakeside setting.\n"
            "24 full hookup RV sites with electric (30/50 AMP).\n"
            "1 Cabin.\n"
            "Approximately 25-30 outdoor storage sites for boat & RV storage, potential for conversion "
            "to additional RV sites.\n"
            "The property is currently owner-managed with minimal marketing or advertising, providing "
            "significant upside potential through professional management & targeted marketing initiatives.\n\n"
            "Investment Advisors\n\n"
            "Kristen Deninno\nFL Lic. # SL3503940\n954.902.5251\nkdeninno@SandsIG.com\n\n"
            "Meagan Brady\nFL Lic. # SL3508397\n954.902.5248\nmbrady@SandsIG.com\n\n"
            "Tom Gorman\nMO Lic. # 2023012377\n610.550.8884\ntom@SandsIG.com\n"
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

    # Window: last 24h from 2026-07-02 06:30 Central = 11:30 UTC
    since = datetime(2026, 7, 1, 11, 30, 0, tzinfo=timezone.utc)
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
        return 0
    else:
        print("\nNo draft created (no qualifying listings or all filtered out).")
        return 0


if __name__ == "__main__":
    sys.exit(main())
