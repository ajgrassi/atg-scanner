"""Live scanner run for 2026-08-08 — feeds today's Gmail MCP data into the pipeline.

Usage:  uv run python run_today.py
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
log = get_logger("run_today")

# ── Emails fetched from Gmail MCP 2026-08-08 ─────────────────────────────
EMAILS: list[dict] = [
    {
        "id": "19fdcc05f245822d",
        "thread_id": "19fdcc05f245822d",
        "sender": "mattm@sandsig.com",
        "subject": (
            "Bonus Depreciation Opportunity | Net Leased Travel Center Portfolio"
            " | Zero LL Responsibilities | Buy One or All"
        ),
        "received_at": "2026-08-07T15:03:42Z",
        "text_body": (
            "Sands Investment Group is pleased to exclusively offer for sale a "
            "Travel Center Portfolio\n\n"
            "Bonus Depreciation | Net Lease Travel Center\n\n"
            "SUMMARY:\n\n"
            "States: NM, GA, LA, AR, TX, IN, MI\n\n"
            "Price Range: $16,000,000 - $65,000,000\n\n"
            "Lease Term: 20 Years\n\n"
            "Tenant: National Tenant\n\n"
            "Rent Increases: 2% Annually\n\n"
            "Landlord Responsibilities: None\n\n"
            "Click Here For More Information\n\n"
            "INVESTMENT SALE ADVISORS:\n\n"
            "MATT MONTAGNE\nTX #695673\n512.920.5120\nmattm@SandsIG.com\n\n"
            "YOSSI FREEMAN\nTX #793232\n512.885.0318\nyossi@SandsIG.com\n\n"
            "TYLER ELLINGER\nTX #690604\n512.643.3700\ntyler@SandsIG.com\n\n"
            "ANDREW ACKERMAN\nNM #20310 | GA #311619\n770.626.0445\nandrew@SandsIG.com\n\n"
            "This Asset May Qualify for Bonus Depreciation.\n\n"
            "Learn how investors are maximizing year-one tax savings in 2026.\n"
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


def main() -> int:
    db.migrate()
    draft_out = Path("data/draft_request.json")
    draft_out.unlink(missing_ok=True)

    messages = build_messages()
    client = PreloadedGmailClient(messages, draft_out)

    since = datetime(2026, 8, 7, 6, 30, 0, tzinfo=timezone.utc)  # 24h window
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
