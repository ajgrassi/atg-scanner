"""Live run for 2026-05-20: feed today's Gmail-fetched emails into the pipeline.

The Gmail MCP fetched 7 threads from sandsig.com (newer_than:1d).
This script builds EmailMessage objects from the extracted text, runs the
full pipeline (parse → dedup → score → digest → draft), then writes
data/run_log.json and returns the draft payload for the MCP caller to create.
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
log = get_logger("run_live_20260520")

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
    # Also strip zero-width non-joiners and hair spaces used to defeat spam filters
    html = re.sub(r"[‌​­‍]", "", html)
    # Strip the ‌ character (Gmail preview-suppression padding)
    html = html.replace("‌", "").replace("‌", "")
    lines = [l.strip() for l in html.splitlines() if l.strip()]
    return "\n".join(lines)


# ── Emails fetched from Gmail MCP 2026-05-20 ────────────────────────────────
# 7 threads from sandsig.com; htmlBody extracted and converted to text below.

THREAD_FILES = [
    ("19e41dc94cb3569b", "toolu_015TxsSfCNUERE5Ac597Wu98.txt",
     "doug@sandsig.com",
     "Development Site | Atlanta MSA",
     "2026-05-19T20:03:47Z"),
    ("19e41a1202e79d65", "toolu_01NLESKHy93jjqVyj5cLLYQb.txt",
     "aackerman@sandsig.com",
     "New Listing | 15,251 SF Shopping Center - Birmingham, AL |  Upside Potential | Strong Traffic Counts",
     "2026-05-19T19:03:54Z"),
    ("19e4171d1661a632", "toolu_01VgUp5LyKjaGAFrLKmAruab.txt",
     "jmulloy@sandsig.com",
     "6.25% CAP | Corporate Arby's | ABS NNN | 40-Year Operating History | Tax Free State",
     "2026-05-19T18:04:01Z"),
    ("19e413485850e551", "toolu_01Qhh1n9f68mQZ3un5jTTR6y.txt",
     "dsaboorian@sandsig.com",
     "For Lease | 6,546 SF Office Space | Immediate Access to I-85 | Move-In Ready",
     "2026-05-19T17:03:47Z"),
    ("19e4103a16a82b69", "toolu_011svYZmmAWssVbFGjcUQnjX.txt",
     "aconley@sandsig.com",
     "100% Leased Retail Center | Below Market Rents | 8.04% CAP | Dominant Retail Corridor",
     "2026-05-19T16:03:58Z"),
    ("19e40cc5ed910d8e", "toolu_01LACSc2fkDjJhpxZM1HW3HV.txt",
     "rsompayrac@sandsig.com",
     "Price Reduction | Turnkey Owner-User Education Facility | Strong Family Demographics & High Demand | Lansing, MI",
     "2026-05-19T15:03:46Z"),
    ("19e4097cf3a5ff57", "toolu_01BYKA4g3UtrNLNDwVBQWzqG.txt",
     "gary@sandsig.com",
     "Turnkey Owner-User Asset | Across Walmart | Business & RE | High Traffic Area",
     "2026-05-19T14:03:57Z"),
]

TOOL_RESULTS_DIR = Path("/root/.claude/projects/-home-user-atg-scanner"
                         "/8f823d00-8f9b-4656-befa-aedb74bf48b2/tool-results")


def _load_message(thread_id: str, filename: str, sender: str, subject: str, received_at: str) -> EmailMessage:
    path = TOOL_RESULTS_DIR / filename
    raw = json.loads(path.read_text(encoding="utf-8"))
    html = raw["messages"][0].get("htmlBody", "")
    text = _html_to_text(html)
    return EmailMessage(
        id=thread_id,
        thread_id=thread_id,
        sender=sender,
        subject=subject,
        received_at=received_at,
        text_body=text,
        html_body=html,
    )


# ── Fake Gmail client ────────────────────────────────────────────────────────

class LiveRunClient:
    """Returns pre-loaded messages; captures draft for MCP caller."""

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
        self._draft_out.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                                   encoding="utf-8")
        self.draft_id = "pending-mcp-create"
        log.info("live_client.draft_saved", path=str(self._draft_out))
        return self.draft_id


# ── Main ────────────────────────────────────────────────────────────────────

def main() -> int:
    db.migrate()

    messages = []
    for args in THREAD_FILES:
        try:
            messages.append(_load_message(*args))
        except Exception as e:
            log.warning("load_message_failed", thread_id=args[0], error=str(e))

    log.info("messages_loaded", count=len(messages))

    draft_out = Path("data/draft_request.json")
    draft_out.parent.mkdir(parents=True, exist_ok=True)
    draft_out.unlink(missing_ok=True)

    client = LiveRunClient(messages, draft_out)

    since = datetime(2026, 5, 19, 6, 30, 0, tzinfo=timezone.utc)

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
        print("\n--- DRAFT (HTML body first 500 chars) ---")
        print(draft["html_body"][:500])
        return 0
    else:
        print("\nNo draft created (no qualifying listings or all filtered — quiet day).")
        return 0


if __name__ == "__main__":
    sys.exit(main())
