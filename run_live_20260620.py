"""Live run for 2026-06-20 (Saturday).

1 broker email found newer_than:1d, from tmcgarry@sandsig.com:
  19ee14ff1622fa00  — Reduced Price | 18-Year Absolute NNN | KFC | 1.5% Annual Increases | 160-Unit Guarantee

No run_log.json in this fresh container. Window: newer_than:1d (Jun 19 11:30 CT / Jun 19 16:30 UTC).

Notes:
  - KFC deal, absolute NNN, $1,518,933, 6.75% cap, 18-yr term, 1.5% escalator, Madisonville KY.
  - channel=car_wash_nnn (default for sandsig non-IOS). Scorer structural gates will fail
    (bonus_dep_eligible=None, roof_structure=None — not in Sands IG broadcast format).
  - Listing persisted to DB; quiet-day digest (no scored rows pass gates).
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
log = get_logger("run_live_20260620")

EMAIL_BODY = """\
Sands Investment Group is Pleased to Exclusively Offer For Sale the 6,164 SF KFC Absolute NNN Asset Located at 197 Madison Square Drive in Madisonville, KY.

https://email.sandsig.com/lt.php?x=4lZy~GDFUqGZ5X_5zg1IUBOhAK_UjgL1k~dgXKPIVqHMDXB9-0y.1OF013IkmNbykMg3bHPKMnah7pR-0Uy7xeFv1n-hiEA0_uc

KFC - Madisonville, KY

PRICE

$1,518,933

CAP
RATE

6.75%

SQUARE FOOTAGE

6,440 SF

Investment Highlights

Brand Strength: Operating under the globally recognized KFC brand, this location benefits from TRG's extensive experience and market presence. With ~140 KFC locations under their management, the combined strength of Tasty Restaurant Group and KFC provides unparalleled stability, making this an attractive and secure investment.
Rent Increases & Options: The lease features 1.5% annual rental increases throughout the initial term and in the option periods, steadily increasing NOI and hedging against inflation.
Strategic Madisonville, KY Location: Located on Hwy 69, this KFC benefits from high visibility and significant traffic, with over 20,000 VPD. The property is well- positioned in a thriving area of Madisonville, ensuring consistent customer traffic and reinforcing its value as a dependable investment.

Investment Advisors

Tyler McGarry

CA Lic. # 02232697

310.558.2029

tmcgarry@SandsIG.com

Adam Scherr

CA Lic. # 01925644

310.853.1266

adam@SandsIG.com

Scott Reid, ParaSell LLC

KY Lic. # 260934

949.942.6585

scott@parasellinc.com

______________________________________________________________________

Broker of Record

Scott Reid

ParaSell, Inc
KY #260934
949.942.6585
scott@parasellinc.com
"""

MESSAGES = [
    EmailMessage(
        id="19ee14ff1622fa00",
        thread_id="19ee14ff1622fa00",
        sender="tmcgarry@sandsig.com",
        subject="Reduced Price | 18-Year Absolute NNN | KFC | 1.5% Annual Increases | 160-Unit Guarantee",
        received_at="2026-06-19T19:03:43Z",
        text_body=EMAIL_BODY,
        html_body="",
    ),
]


class LiveRunClient:
    """Minimal GmailClient shim — wraps pre-fetched messages, saves draft to disk."""

    def __init__(self, messages: list[EmailMessage], draft_out: Path) -> None:
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
            "text_body": getattr(draft, "text_body", ""),
        }
        self._draft_out.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        self.draft_id = "pending-mcp-create"
        log.info("live_client.draft_saved", path=str(self._draft_out))
        return self.draft_id


def main() -> int:
    db.migrate()

    draft_out = Path("data/draft_request.json")
    draft_out.parent.mkdir(parents=True, exist_ok=True)
    draft_out.unlink(missing_ok=True)

    client = LiveRunClient(MESSAGES, draft_out)

    # newer_than:1d from 6:30 AM CT on Jun 20 = Jun 19 11:30 UTC
    since = datetime(2026, 6, 19, 11, 30, 0, tzinfo=timezone.utc)

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
        print("\n--- DRAFT HTML BODY (first 500 chars) ---")
        print(draft.get("html_body", "")[:500])
    else:
        print("\nNo draft created — quiet day (no listings passed structural gates).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
