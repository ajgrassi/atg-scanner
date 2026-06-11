"""Live run for 2026-06-11 (Thursday).

3 broker threads found newer_than:1d, all from sandsig.com:
  1. 19eb22f7e7a91d7b  info@sandsig.com          — RV Park Deals blast (3 properties)
  2. 19eb21886a00edf3  skrepistman@sandsig.com   — New Creations Child Care, St. Michael MN
  3. 19eb1b499499071c  dan@sandsig.com            — Price Reduced Chipotle, Gardner MA

No run_log.json in this fresh container. Window: newer_than:1d (Jun 10 UTC).
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from app import db, pipeline
from app.gmail_client import DraftRequest, EmailMessage
from app.utils import configure_logging, get_logger

configure_logging()
log = get_logger("run_live_20260611")

TOOL_RESULTS_DIR = Path(
    "/root/.claude/projects/-home-user-atg-scanner"
    "/ca01c8fa-a8de-5e29-b26d-bd1dd4845178/tool-results"
)

THREADS = [
    {
        "thread_id": "19eb22f7e7a91d7b",
        "file": "toolu_01Cr2Mvg2hmxtcwHCU4kbisr.txt",
        "sender": "info@sandsig.com",
        "subject": "RV Park Deals For Andrew",
        "received_at": "2026-06-10T15:33:55Z",
    },
    {
        "thread_id": "19eb21886a00edf3",
        "file": "toolu_01VHM52GK5YCL1FAksBNKwjJ.txt",
        "sender": "skrepistman@sandsig.com",
        "subject": "New Listing | 7.00% CAP | 12 Yr Child Care NNN Asset | 2% Annual Increases",
        "received_at": "2026-06-10T15:03:43Z",
    },
    {
        "thread_id": "19eb1b499499071c",
        "file": "toolu_01DnMh7PjG9cHRPs6b68HKmf.txt",
        "sender": "dan@sandsig.com",
        "subject": "Price Reduced | Chipotle (2024) | Outparcel to ALDI/Tractor Supply | 10-Yr Corporate Lease",
        "received_at": "2026-06-10T13:03:54Z",
    },
]


def _html_to_text(html: str) -> str:
    html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<(?:br|p|div|tr|td|li|h[1-6])[^>]*>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"<[^>]+>", " ", html)
    for ent, rep in [
        ("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
        ("&#39;", "'"), ("&quot;", '"'), ("&zwnj;", ""), ("&#8211;", "–"),
        ("&#8217;", "'"), ("&#8216;", "'"), ("&#8220;", '"'), ("&#8221;", '"'),
    ]:
        html = html.replace(ent, rep)
    html = re.sub(r"[‌​­‍]", "", html)
    lines = [l.strip() for l in html.splitlines() if l.strip()]
    return "\n".join(lines)


def _load_message(t: dict) -> EmailMessage:
    path = TOOL_RESULTS_DIR / t["file"]
    raw = json.loads(path.read_text(encoding="utf-8"))
    msg = raw["messages"][0]
    html = msg.get("htmlBody", "") or ""
    text = _html_to_text(html)
    return EmailMessage(
        id=t["thread_id"],
        thread_id=t["thread_id"],
        sender=t["sender"],
        subject=t["subject"],
        received_at=t["received_at"],
        text_body=text,
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

    # newer_than:1d window — Jun 10 06:30 AM CT = Jun 10 11:30 UTC
    since = datetime(2026, 6, 10, 11, 30, 0, tzinfo=timezone.utc)

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
        return 0
    else:
        print("\nNo draft created (quiet day — no qualifying listings).")
        return 0


if __name__ == "__main__":
    sys.exit(main())
