"""Live scanner run for 2026-08-14 — feeds today's Gmail MCP data into the pipeline.

Emails found today:
  1. prider@sandsig.com — "Confidential Deal | Operating Childcare Center - Cherokee County, SC"
     → Sands IG parser, car_wash_nnn channel
     → No street address (only county+state), will produce no listing
  2. teresa@aec-kc.com — "Information Packets for the month of July"
     → AEF parser, oil_gas_wi channel
     → Monthly investor reporting email (not a new deal), no address/price

Expected: 0 qualifying listings → no draft created.

Usage:  uv run python run_live_20260814.py
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
log = get_logger("run_live_20260814")

EMAILS: list[dict] = [
    {
        "id": "19ff7250775465c4",
        "thread_id": "19ff7250775465c4",
        "sender": "prider@sandsig.com",
        "subject": "Confidential Deal | Operating Childcare Center - Cherokee County, SC",
        "received_at": "2026-08-12T18:03:46Z",
        "text_body": (
            "Sands Investment Group is pleased to present for sale a confidential deal."
            "https://sandsig.com/\n\n"
            "****CONFIDENTIAL**\n\n**OPPORTUNITY****\n\n**CONFIDENTIAL**\n\n**DEAL**\n\n"
            "Asset Type \n\n    Childcare Center\n\n"
            "Deal\n\n    Operations with Real Estate\n\n"
            "Building Size\n\n    4,176 SF\n\n"
            "Price\n\n    $1,750,000\n\n"
            "Price/SF\n\n    $419.06\n\n"
            "Location\n\n    Cherokee County, SC\n\n"
            "**INVESTMENT ADVISOR**\n\nPEYTON RIDER\n\nSands Investment Group\n\n"
            "SC Lic. # 145108\n\n843.938.4339\n\nprider@SandsIG.com\n\n"
            "Please reach out to our Sands Investment Group team for additional details and the NDA.\n"
        ),
    },
    {
        "id": "19ffd0c6470fedf3",
        "thread_id": "19ffd0c6470fedf3",
        "sender": "teresa@aec-kc.com",
        "subject": "Information Packets for the month of July",
        "received_at": "2026-08-13T21:34:06Z",
        "text_body": (
            "Attached are the Information Packets for your corresponding Alliance Energy Fund "
            "Investments for the month of July. You can also find these in your SmartVault portal "
            "(along with other important documents like your distribution statements, Tax Forms, "
            "and other communications). You can access your portal here - SmartVault Portal"
            "<https://aec-kc.smartvault.com/secure/SignIn.aspx>.\n\n"
            "Thank you,\n\nTeresa Putthoff\n\nAlliance Equities Corporation\n"
            "7240 W 98th Terrace\nOverland Park, KS 66212\n"
            "Phone: 913-428-8278\nFax: 913-428-8279\n\n"
            "This communication and any accompanying information is confidential and is only "
            "intended for the person(s) to whom it is addressed."
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

    since = datetime(2026, 8, 13, 6, 30, 0, tzinfo=timezone.utc)  # 24h window

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
