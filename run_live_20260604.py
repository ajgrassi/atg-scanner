"""Live run for 2026-06-04: feed today's Gmail-fetched emails into the pipeline.

6 threads from sandsig.com fetched via Gmail MCP newer_than:1d.
Converts HTML → text, runs parse→score→digest, writes draft_request.json.
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
log = get_logger("run_live_20260604")

# ── HTML → plain-text ────────────────────────────────────────────────────────

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
    html = html.replace("‌", "").replace("‌", "")
    lines = [l.strip() for l in html.splitlines() if l.strip()]
    return "\n".join(lines)


# ── Thread metadata + file refs ───────────────────────────────────────────────

TOOL_RESULTS_DIR = Path(
    "/root/.claude/projects/-home-user-atg-scanner"
    "/98554eb5-01df-4699-97e2-0144a104565c/tool-results"
)

THREADS = [
    {
        "thread_id": "19e8ee12f90c62e3",
        "file": "toolu_015S3kjDZUWkHaaB2F8eGSVV.txt",
        "sender": "jlevine@sandsig.com",
        "subject": "Just Listed | Advance Auto Anchored Retail Center | Value-Add Upside | Richlands, VA",
        "received_at": "2026-06-03T19:03:57Z",
    },
    {
        "thread_id": "19e8eaf8daeadbac",
        "file": "toolu_01JAZkuMLgzkBn4ThLdSvTn5.txt",
        "sender": "ccoassin@sandsig.com",
        "subject": "Prime Location | NNN Gerber Collision & Glass | Recently Renovated | 25+ Year History | High-Traffic - Raleigh, NC",
        "received_at": "2026-06-03T18:03:46Z",
    },
    {
        "thread_id": "19e8e730c9bfbddc",
        "file": "toolu_01K9rdoWmWh48QwhzpEYFcJS.txt",
        "sender": "kdunn@sandsig.com",
        "subject": "For Lease | Move-In Ready Retail/Office Space | Lebanon Road Commons | Hickory, TN",
        "received_at": "2026-06-03T17:03:51Z",
    },
    {
        "thread_id": "19e8e40afaedc475",
        "file": "toolu_01ThfqdvDX48BXvBojQDs7Po.txt",
        "sender": "stratton@sandsig.com",
        "subject": "Rare Charleston NNN Industrial | 7% CAP Rate | 3% Annual Increases | North Charleston, SC",
        "received_at": "2026-06-03T16:03:36Z",
    },
    {
        "thread_id": "19e8e060d29b39c5",
        "file": "toolu_017fo4rTKb5h5tvnjJLddzHq.txt",
        "sender": "wsteinman@sandsig.com",
        "subject": "Just Listed | Prime Dallas Submarket | Owner/User Opportunity | Garland, TX",
        "received_at": "2026-06-03T15:03:58Z",
    },
    {
        "thread_id": "19e8dd730fa84802",
        "file": "toolu_01Jh4RwxQSqpaVdhj1kR5rAK.txt",
        "sender": "dave@sandsig.com",
        "subject": "Whataburger - New Construction | Long-Term Ground Lease | Prime Frontage on Busy Corridor",
        "received_at": "2026-06-03T14:03:48Z",
    },
]


def _load_message(t: dict) -> EmailMessage:
    path = TOOL_RESULTS_DIR / t["file"]
    raw = json.loads(path.read_text(encoding="utf-8"))
    html = raw["messages"][0].get("htmlBody", "")
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


# ── Fake Gmail client ────────────────────────────────────────────────────────

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


# ── Main ────────────────────────────────────────────────────────────────────

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

    # Today's run window: since yesterday 6:30 AM CT = 11:30 UTC
    since = datetime(2026, 6, 3, 11, 30, 0, tzinfo=timezone.utc)

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
        print("\n--- DRAFT (HTML body first 800 chars) ---")
        print(draft["html_body"][:800])
        return 0
    else:
        print("\nNo draft created (quiet day — no qualifying listings).")
        return 0


if __name__ == "__main__":
    sys.exit(main())
