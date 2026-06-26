"""ATG Deal Scanner — live run 2026-06-26.

One broker email found via Gmail MCP (newer_than:1d).
Thread ID: 19efef52ab9d3117 — Sands IG / Gerber Collision + Baker's Towing, Texarkana TX.

Usage: uv run python run_live_20260626.py
Writes: data/draft_request.json  (if digest warranted)
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
log = get_logger("run_live_20260626")

# ── Email fetched live from Gmail MCP (2026-06-26 06:30 CT) ───────────────
# One matching thread in the last 24h from all broker domains.
EMAIL_TEXT = """\
Sands Investment Group is pleased to exclusively offer for sale the 24,550 SF \
Joe Hudson's Collision Center and Baker's Towing & Recovery located at \
3327 & 3407 S Lake Drive in Texarkana, Texas.

Gerber Collision & Glass and Baker's Towing - Texarkana, TX

PRICE
$2,950,000

CAP RATE
7.67%

SQUARE FOOTAGE
24,550 SF

Investment Highlights
Strong Anchor Tenant Net Lease: Collision center occupied by Gerber Collision \
& Glass, a multi-location national collision repair operator with 1300+ locations \
across the United States. Gerber Collision & Glass operates under The Boyd Group \
Services Inc. (BGSI).
Baker's Towing & Recovery: Baker's Towing & Recovery operates one of the most \
comprehensive heavy-duty fleets in the Texarkana region, with service coverage \
extending across both Texas and Arkansas.
Double Net (NN) Leases: Minimal landlord responsibilities with stable in-place \
income across both.
~9 Years of Term Remaining on both leases.
3% Annual Rent Increases provide growing NOI.
Prime Automotive Corridor: Located along S Lake Drive (State Highway 93), a \
heavily trafficked commercial route with strong visibility and direct access.

Investment Advisors
Bryce Pugh  NC Lic. # 347566
704.912.5085
bpugh@SandsIG.com

Clayton Coassin  CT Lic. # RES.0823815
704.498.8902
ccoassin@SandsIG.com

Gary W. Berwick, CCIM  NC Lic. # 312724
980.729.5648
gary@SandsIG.com
"""

EMAILS = [
    EmailMessage(
        id="19efef52ab9d3117",
        thread_id="19efef52ab9d3117",
        sender="bpugh@sandsig.com",
        subject="Price Reduced | 7.67% Cap Rate | 3% Annual Rent Increases| ~9 Years of Term Remaining",
        received_at="2026-06-25T13:04:41Z",
        text_body=EMAIL_TEXT,
    ),
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


def main() -> int:
    db.migrate()
    draft_out = Path("data/draft_request.json")
    draft_out.unlink(missing_ok=True)

    client = PreloadedGmailClient(EMAILS, draft_out)
    since = datetime(2026, 6, 25, 11, 30, 0, tzinfo=timezone.utc)

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
        print("\nNo draft created (no qualifying listings or all filtered out).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
