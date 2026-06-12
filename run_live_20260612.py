"""Live run for 2026-06-12 (Friday).

3 broker threads found newer_than:1d, all from sandsig.com:
  1. 19eb81bef2dfd34f  max@sandsig.com        — Price Reduction | KinderCare | Minneapolis MN
  2. 19eb7b6a5cb17d33  kdunn@sandsig.com      — Just Listed | Value-Add Office | Nashville MSA
  3. 19eb73ed9e648f6a  agilbert@sandsig.com   — Just Listed | Childcare Network | Raleigh MSA

No run_log.json in this fresh container. Window: newer_than:1d (Jun 11 11:30 UTC).
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
log = get_logger("run_live_20260612")

TOOL_RESULTS_DIR = Path(
    "/root/.claude/projects/-home-user-atg-scanner"
    "/12ee0cb3-f629-53a0-a1dd-124925fd2104/tool-results"
)

THREADS = [
    {
        "thread_id": "19eb81bef2dfd34f",
        "file": "toolu_014W3AFVrMotsq8bt11hcckB.txt",
        "sender": "max@sandsig.com",
        "subject": "Price Reduction | Corporate-Backed KinderCare | Minneapolis MSA | 2% Annual Increases",
        "received_at": "2026-06-11T19:03:53Z",
    },
    {
        "thread_id": "19eb7b6a5cb17d33",
        "file": "toolu_01BUHzXKKxQe9fFGE2tdLeAt.txt",
        "sender": "kdunn@sandsig.com",
        "subject": "Just Listed | 16,678 SF Office Building with Immediate Upside | Flexible Use Potential | Nashville MSA",
        "received_at": "2026-06-11T17:14:57Z",
    },
    {
        "thread_id": "19eb73ed9e648f6a",
        "file": "toolu_01YJxDCLnaJsEGuGwB461gjP.txt",
        "sender": "agilbert@sandsig.com",
        "subject": "Just Listed | Under $1M | Childcare Network - Raleigh MSA | 10 Yrs Remaining | 3% Annual Increases",
        "received_at": "2026-06-11T15:03:54Z",
    },
]


def _load_message(t: dict) -> EmailMessage:
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

    # newer_than:1d window — Jun 11 06:30 AM CT = Jun 11 11:30 UTC
    since = datetime(2026, 6, 11, 11, 30, 0, tzinfo=timezone.utc)

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
        print("\nNo draft created (no qualifying listings — all failed structural gates).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
