"""Live run for 2026-06-16 (Tuesday).

3 broker threads found newer_than:1d, all from sandsig.com:
  1. 19eccab30f3ad0b5  info@sandsig.com       — Immediate Buyer Needs (not a listing, skip)
  2. 19ecbdaa764e3d3b  agilbert@sandsig.com   — New Listing | $937,594 | Childcare Network - Garner NC
  3. 19ecb729f89a1194  prider@sandsig.com     — Price Reduced | Vacant Owner-User | Memphis TN 8,084 SF

No run_log.json in this fresh container. Window: newer_than:1d (Jun 15 11:30 UTC).
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
log = get_logger("run_live_20260616")

TOOL_RESULTS_DIR = Path(
    "/root/.claude/projects/-home-user-atg-scanner"
    "/411db356-d7c7-56e2-8d3b-cef573ad8e36/tool-results"
)

THREADS = [
    {
        "thread_id": "19eccab30f3ad0b5",
        "file": None,  # inline — buyer needs blast, no listing
        "sender": "info@sandsig.com",
        "subject": "Immediate Buyer Needs",
        "received_at": "2026-06-15T19:03:51Z",
        "text_body": (
            "Buyer Needs\n\n"
            "SIG is working with multiple buyers who have immediate needs for investment purposes\n\n"
            "Access our full list of Buyer Needs when you create your account.\n"
        ),
    },
    {
        "thread_id": "19ecbdaa764e3d3b",
        "file": "toolu_013rYg6QqSJkQNsHwgSuaN9V.txt",
        "sender": "agilbert@sandsig.com",
        "subject": "New Listing | $937,594 | Childcare Network - 272 Unit Corp. Guarantee | Raleigh MSA | 3% Annual Increases | 10 Yrs Remaining",
        "received_at": "2026-06-15T15:04:51Z",
    },
    {
        "thread_id": "19ecb729f89a1194",
        "file": "toolu_01FDETFEmBHSkyfnvhjyKuti.txt",
        "sender": "prider@sandsig.com",
        "subject": "Price Reduced | Vacant Owner-User Asset | High-Demand Memphis Corridor | 8,084 SF",
        "received_at": "2026-06-15T13:04:29Z",
    },
]


def _load_message(t: dict) -> EmailMessage:
    if t.get("text_body") is not None:
        return EmailMessage(
            id=t["thread_id"],
            thread_id=t["thread_id"],
            sender=t["sender"],
            subject=t["subject"],
            received_at=t["received_at"],
            text_body=t["text_body"],
            html_body="",
        )
    path = TOOL_RESULTS_DIR / t["file"]
    raw = json.loads(path.read_text(encoding="utf-8"))
    msg = raw["messages"][0]
    plain = (msg.get("plaintextBody") or "").replace("\xa0", " ")
    html = msg.get("htmlBody", "") or ""
    return EmailMessage(
        id=t["thread_id"],
        thread_id=t["thread_id"],
        sender=t["sender"],
        subject=t["subject"],
        received_at=t["received_at"],
        text_body=plain,
        html_body=html,
    )


class LiveRunClient:
    def __init__(self, messages: list[EmailMessage], draft_out: Path):
        self._messages = messages
        self._draft_out = draft_out
        self.draft_id: str | None = None

    def search(self, query: str, max_results: int = 100) -> list[EmailMessage]:
        log.info("live_client.search", returning=len(self._messages))
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
        self._draft_out.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        self.draft_id = "pending-mcp-create"
        log.info("live_client.draft_saved", path=str(self._draft_out))
        return self.draft_id


def main() -> int:
    db.migrate()

    messages = []
    for t in THREADS:
        try:
            messages.append(_load_message(t))
        except Exception as e:
            log.warning("load_message_failed", thread_id=t["thread_id"], error=str(e))

    log.info("messages_loaded", count=len(messages))

    draft_out = Path("data/draft_request.json")
    draft_out.parent.mkdir(parents=True, exist_ok=True)
    draft_out.unlink(missing_ok=True)

    client = LiveRunClient(messages, draft_out)

    # newer_than:1d window — Jun 15 06:30 AM CT = Jun 15 11:30 UTC
    since = datetime(2026, 6, 15, 11, 30, 0, tzinfo=timezone.utc)

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
    rows = rows[-365:]
    log_path.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")

    print(json.dumps(
        {k: v for k, v in summary.items() if k != "gmail_query"},
        indent=2, default=str,
    ))

    if draft_out.exists():
        draft = json.loads(draft_out.read_text(encoding="utf-8"))
        print("\n--- DRAFT SUBJECT ---")
        print(draft["subject"])
        print("\n--- DRAFT TEXT BODY (first 2000 chars) ---")
        print(draft.get("text_body", "")[:2000])
    else:
        print("\nNo draft created (quiet day — no qualifying listings).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
