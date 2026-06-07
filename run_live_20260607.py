"""Live run for 2026-06-07 (Sunday): process unprocessed Jun 4-5 Sands IG emails.

No run_log.json exists (fresh container). Extended window to newer_than:3d to
catch emails missed since last successful run (2026-06-04).

10 threads from sandsig.com; 1 marketing email skipped (info@sandsig.com).
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
log = get_logger("run_live_20260607")

TOOL_RESULTS_DIR = Path(
    "/root/.claude/projects/-home-user-atg-scanner"
    "/a5c53d9d-6d25-53a6-b269-93be44ab9335/tool-results"
)

THREADS = [
    # ── Jun 5 batch ─────────────────────────────────────────────────────────
    {
        "thread_id": "19e98f5cb12a0cac",
        "file": "toolu_019Wbo8EKqni8RDQWQVrj7Lg.txt",
        "sender": "dgarson@sandsig.com",
        "subject": "New Listing | Mister Car Wash | $350/SF | Corporate Ground Lease | Rare Low-Basis Entry Point",
        "received_at": "2026-06-05T18:03:35Z",
    },
    {
        "thread_id": "19e98c065e062818",
        "file": "toolu_01JpCjtB1cuHWfvSGTdqCpU9.txt",
        "sender": "aanttila@sandsig.com",
        "subject": "New Listing | 20,900 SF Value-Add Retail Center | Strong Upside & Flexible Re-Tenanting",
        "received_at": "2026-06-05T17:03:40Z",
    },
    {
        "thread_id": "19e9851bea4bd4ff",
        "file": "toolu_016cgyPzP5etwhuCMtnPQ8yp.txt",
        "sender": "hkirby@sandsig.com",
        "subject": "Just Listed | SiteOne (NYSE: SITE) | 3.5% Annual Increases | Cheap Rent | Long Term Lease | Columbia, SC",
        "received_at": "2026-06-05T15:03:35Z",
    },
    {
        "thread_id": "19e981ada237211a",
        "file": "toolu_01VyRd2Y9aMmdcKJ6vFFc954.txt",
        "sender": "mwatson@sandsig.com",
        "subject": "Reduced Price | Pensacola, FL - Tax Free State |14+Year NNN Urgent Care | Strong Operator",
        "received_at": "2026-06-05T14:03:36Z",
    },
    {
        "thread_id": "19e97e6272b3faa8",
        "file": "toolu_01QYEDxetEACJUBDqMZ616xL.txt",
        "sender": "skrepistman@sandsig.com",
        "subject": "Just Listed | 7.00% CAP | 12+ Year Lease Child Care Asset | 2% Annual Increases",
        "received_at": "2026-06-05T13:03:41Z",
    },
    # ── Jun 4 batch ─────────────────────────────────────────────────────────
    {
        "thread_id": "19e93d7fca3aae23",
        "file": "toolu_01K4KDjsN7qyibxKSK7fk688.txt",
        "sender": "jliberatore@sandsig.com",
        "subject": "Advance Auto Parts | Corporate Guarantee | 7.25% CAP",
        "received_at": "2026-06-04T18:06:30Z",
    },
    {
        "thread_id": "19e939955c20e127",
        "file": "toolu_01M9NwHyc3QdxZZ7nGpz3uPJ.txt",
        "sender": "cayson@sandsig.com",
        "subject": "Just Listed | Dollar Tree | Walmart Outparcel | Austin MSA | $2M",
        "received_at": "2026-06-04T17:03:54Z",
    },
    {
        "thread_id": "19e932bd339694a7",
        "file": "toolu_01JF2vFhrXNngarNfKjXiaqh.txt",
        "sender": "zboals@sandsig.com",
        "subject": "2,500 SF For Lease | High-Traffic Odessa Corridor | Flexible Space & Long-Term Stability",
        "received_at": "2026-06-04T15:03:39Z",
    },
    {
        "thread_id": "19e92fe356d066d3",
        "file": "toolu_01B9Vp8Sh4nCs6C82BB67Aq8.txt",
        "sender": "jmulloy@sandsig.com",
        "subject": "7.20% CAP NNN Applebee's | Proven Operator (130+ Units) | Fort Wayne, IN MSA | 4% Buyside Commission",
        "received_at": "2026-06-04T14:03:50Z",
    },
    {
        "thread_id": "19e92bdc05019afc",
        "file": "mcp-Gmail-get_thread-1780832064255.txt",
        "sender": "bpatterson@sandsig.com",
        "subject": "Price Reduced | Fully Leased Medical & Office Park | 7.58% CAP | DaVita Anchored | Development Opportunity",
        "received_at": "2026-06-04T13:03:50Z",
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
    html = html.replace("‌", "").replace("‌", "")
    lines = [l.strip() for l in html.splitlines() if l.strip()]
    return "\n".join(lines)


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

    # Extended window: since Jun 4 6:30 AM CT = Jun 4 11:30 UTC
    # (no run_log.json in this fresh container)
    since = datetime(2026, 6, 4, 11, 30, 0, tzinfo=timezone.utc)

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
        print("\n--- DRAFT TEXT BODY (first 1200 chars) ---")
        print(draft.get("text_body", "")[:1200])
        return 0
    else:
        print("\nNo draft created (quiet day — no qualifying listings).")
        return 0


if __name__ == "__main__":
    sys.exit(main())
