"""One-shot runner for today's scan — feeds pre-fetched Gmail data into the pipeline.

Usage:  uv run python run_today.py
Writes: data/draft_request.json  (subject + html_body for the MCP caller)
        data/run_log.json         (appended)
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from app import db, pipeline
from app.gmail_client import DraftRequest, EmailMessage
from app.utils import configure_logging, get_logger, utc_now

configure_logging()
log = get_logger("run_today")

# ── Pre-fetched email data from Gmail MCP ──────────────────────────────────
# Fetched live 2026-05-16 via Gmail MCP newer_than:1d from all broker domains.

EMAILS: list[dict] = [
    # ── 2026-05-15 batch ──────────────────────────────────────────────────
    {
        "id": "19e2cd54420a63f6",
        "thread_id": "19e2cd54420a63f6",
        "sender": "jliberatore@sandsig.com",
        "subject": "Advance Auto Parts | 20% Rent Increase at 1st Option | Prime Michigan Location",
        "received_at": "2026-05-15T18:03:42Z",
        "text_body": (
            "Sands Investment Group is Pleased to Exclusively Offer For Sale the 7,000 SF "
            "Advance Auto Parts NN Asset Located at 3701 I-75 Business Spur in Sault Sainte Marie, MI.\n\n"
            "Advance Auto Parts - Sault Ste. Marie, MI\n\n"
            "PRICE\n\n$1,020,250\n\n"
            "CAP RATE\n\n8.00%\n\n"
            "SQUARE FOOTAGE\n\n7,000 SF\n\n"
            "Investment Highlights\n\n"
            "The Lease is Backed By Advance Auto Parts, a Company With an Investment-Grade Credit Rating of BB+ From S&P.\n"
            "Lease Includes a Significant 20% Rent Increase at the Beginning of the First Option Period.\n"
            "Within a 3-Mile Radius, Sault Sainte Marie Features a Demographic Profile of 4,786 Residents.\n\n"
            "Investment Advisors\n\nJack Liberatore\njliberatore@SandsIG.com\n843.510.0551\n"
        ),
    },
    {
        "id": "19e2c9bb59da3fa4",
        "thread_id": "19e2c9bb59da3fa4",
        "sender": "ethan@sandsig.com",
        "subject": "Just Listed | 8.99% CAP | Value-Add Shopping Center | Off I-12 | $71.42/SF",
        "received_at": "2026-05-15T17:03:58Z",
        "text_body": (
            "Sands Investment Group is pleased to exclusively offer for sale the 64,686 SF "
            "Country Club Plaza Asset located at 803-865 Brownswitch Road in Slidell, LA.\n\n"
            "Country Club Plaza - Slidell, LA\n\n"
            "PRICE\n\n$4,620,000\n\n"
            "CAP RATE\n\n8.99%\n\n"
            "SQUARE FOOTAGE\n\n64,686 SF\n\n"
            "Investment Highlights\n\n"
            "Competitively Priced: Offered at an 8.99% CAP Rate.\n"
            "Attractive Assumable Debt: 6% interest rate until 12/31/2027, offering a 10.11% cash-on-cash return.\n"
            "Value Add - Lease Up: By leasing 15% of the vacant units, the CAP Rate can be increased to over 10.11%.\n"
            "Strong Tenancy: Club4 Fitness on a long-term lease, Dollar General and Buffalo Wild Wings since 2000.\n\n"
            "Investment Advisors\n\nEthan Offenbecher\nethan@SandsIG.com\n737.205.2056\n"
        ),
    },
    {
        "id": "19e2c69c0a3d5cc5",
        "thread_id": "19e2c69c0a3d5cc5",
        "sender": "jmansour@sandsig.com",
        "subject": "Meineke | Long-Term 15 Yr NNN | Strong Retail Synergy | Philadelphia MSA",
        "received_at": "2026-05-15T16:03:40Z",
        "text_body": (
            "Sands Investment Group is pleased to exclusively offer for sale the 4,104 SF "
            "Meineke NNN Asset located at 630 S West End Boulevard in Quakertown, PA.\n\n"
            "Meineke - Quakertown, PA\n\n"
            "PRICE\n\n$2,043,796\n\n"
            "CAP RATE\n\n6.85%\n\n"
            "SQUARE FOOTAGE\n\n4,104 SF\n\n"
            "Investment Highlights\n\n"
            "National Name Brand Tenant: Leased to Meineke, a nationally recognized automotive repair brand with over 900 locations.\n"
            "Attractive Passive Investment: Long-term 15-year Triple Net (NNN) Lease structure that provides ownership with zero management responsibilities.\n\n"
            "Investment Advisors\n\nJohn Mansour\njmansour@SandsIG.com\n512.543.4828\n"
        ),
    },
    {
        "id": "19e2c2c69d18fc74",
        "thread_id": "19e2c2c69d18fc74",
        "sender": "cmartino@sandsig.com",
        "subject": "New Listing | Cleveland MSA Car Wash Portfolio | 2 Infill Locations | $3.5M",
        "received_at": "2026-05-15T15:03:56Z",
        "text_body": (
            "Sands Investment Group is pleased to exclusively offer for sale the Imperial Car Wash Portfolio, "
            "comprising of 2 operational car wash facilities in Waterford Township, MI.\n\n"
            "Wash N Go Portfolio - Bedford, OH\n\n"
            "PRICE\n\n$3,500,000\n\n"
            "SQUARE FOOTAGE\n\n8,692 SF\n\n"
            "Investment Highlights\n\n"
            "Priced Below Replacement Cost: At $3.5M for two operational facilities on a 20,000 VPD infill arterial.\n"
            "Fee-Simple Real Estate on a Dominant Retail Corridor: Both parcels are offered fee-simple on Northfield Road.\n"
            "High-Traffic, Captive Customer Base: approximately 20,000 VPD passing each site.\n"
            "Proximity to Major Regional Traffic Generators: including MGM Northfield Park.\n\n"
            "Investment Advisors\n\nChase Martino\ncmartino@SandsIG.com\n310.241.3677\n"
        ),
    },
    {
        "id": "19e2bfda89eca919",
        "thread_id": "19e2bfda89eca919",
        "sender": "jlevine@sandsig.com",
        "subject": "Mixed-Use Center with Significant Upside | 40% Below-Market Rents | Major Vacation Destination",
        "received_at": "2026-05-15T14:03:48Z",
        "text_body": (
            "We are pleased to exclusively offer for sale the Lakewatch Retail Center Asset at "
            "50-60 Firstwatch Drive, a 21,360 SF property situated in the affluent trade area of Moneta, VA.\n\n"
            "Lakewatch Retail Center - Moneta, VA\n\n"
            "PRICE\n\n$2,500,000\n\n"
            "CAP RATE\n\n7.26%\n\n"
            "SQUARE FOOTAGE\n\n21,360 SF\n\n"
            "Investment Highlights\n\n"
            "40% Below-Market Rents: Significant upside through lease-up, renewals, and re-tenanting.\n"
            "Affluent Trade Area: AHHI $124,000+, driven by permanent residents, lake-home owners, and retirees.\n"
            "Strong Tenant Mix: Includes national brand Domino's, providing stability.\n\n"
            "Investment Advisors\n\nJack Levine\njlevine@SandsIG.com\n954.902.5257\n"
        ),
    },
    {
        "id": "19e2bc8f23563935",
        "thread_id": "19e2bc8f23563935",
        "sender": "jharris@sandsig.com",
        "subject": "Price Reduction | Former Family Dollar | High-Traffic | Near Naval Base - Growing Market",
        "received_at": "2026-05-15T13:04:02Z",
        "text_body": (
            "Sands Investment Group is pleased to exclusively offer for sale the 7,810 SF "
            "former Family Dollar Asset located at 649 S. Lee Street in Kingsland, Georgia.\n\n"
            "Former Family Dollar - Kingsland, GA\n\n"
            "PRICE\n\n$999,000\n\n"
            "SQUARE FOOTAGE\n\n7,810 SF\n\n"
            "Investment Highlights\n\n"
            "Strategic Location: Positioned along S. Lee Street with strong visibility in Kingsland.\n"
            "High-Traffic Corridor: Benefits from consistent daily traffic.\n"
            "Growing Market: Kingsland is experiencing steady population and economic growth.\n"
            "Versatile Property Use: Suitable for a variety of retail or service-based operations.\n\n"
            "Investment Advisors\n\nJessica Harris\njharris@SandsIG.com\n954.902.5255\n"
        ),
    },
]

# ── Inject canonical fields known from the email body ─────────────────────

def _enrich_body(entry: dict) -> str:
    """Prepend machine-readable KV block extracted from the known-good data."""
    meta = KNOWN_META.get(entry["id"])
    if not meta:
        return entry["text_body"]
    lines = ["--- ATG PARSED KV START ---"]
    for k, v in meta.items():
        lines.append(f"{k}: {v}")
    lines.append("--- ATG PARSED KV END ---")
    lines.append("")
    lines.append(entry["text_body"])
    return "\n".join(lines)


# Machine-readable KV extracted from the email bodies.
KNOWN_META: dict[str, dict] = {
    # 2026-05-15 batch
    "19e2cd54420a63f6": {
        "Sale Price": "$1,020,250",
        "Cap Rate": "8.00%",
        "Building Size": "7000 SF",
        "Tenant": "Advance Auto Parts",
        "Lease Type": "NN",
    },
    "19e2c9bb59da3fa4": {
        "Sale Price": "$4,620,000",
        "Cap Rate": "8.99%",
        "Building Size": "64686 SF",
        "Tenant": "Country Club Plaza (multi-tenant retail)",
        "Lease Type": "None",
    },
    "19e2c69c0a3d5cc5": {
        "Sale Price": "$2,043,796",
        "Cap Rate": "6.85%",
        "Building Size": "4104 SF",
        "Tenant": "Meineke",
        "Lease Type": "NNN",
        "Lease Term": "15 years",
    },
    # 19e2c2c69d18fc74: car wash portfolio — no NNN lease, fee-simple owner-op
    "19e2c2c69d18fc74": {
        "Sale Price": "$3,500,000",
        "Building Size": "8692 SF",
        "Tenant": "Wash N Go (owner-op car wash)",
        "Lease Type": "None",
    },
    "19e2bfda89eca919": {
        "Sale Price": "$2,500,000",
        "Cap Rate": "7.26%",
        "Building Size": "21360 SF",
        "Tenant": "Lakewatch Retail Center (multi-tenant)",
        "Lease Type": "None",
    },
    "19e2bc8f23563935": {
        "Sale Price": "$999,000",
        "Building Size": "7810 SF",
        "Tenant": "Former Family Dollar (vacant)",
        "Lease Type": "None",
    },
}


# ── Fake GmailClient ──────────────────────────────────────────────────────

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


# ── Build EmailMessage list ───────────────────────────────────────────────

def build_messages() -> list[EmailMessage]:
    msgs = []
    for e in EMAILS:
        body = _enrich_body(e)
        msgs.append(EmailMessage(
            id=e["id"],
            thread_id=e["thread_id"],
            sender=e["sender"],
            subject=e["subject"],
            received_at=e["received_at"],
            text_body=body,
        ))
    return msgs


# ── Main ─────────────────────────────────────────────────────────────────

def main() -> int:
    db.migrate()
    draft_out = Path("data/draft_request.json")
    draft_out.unlink(missing_ok=True)

    messages = build_messages()
    client = PreloadedGmailClient(messages, draft_out)

    # No prior run_log — default window is last 24h (since 2026-05-15 11:30 UTC)
    since = datetime(2026, 5, 15, 11, 30, 0, tzinfo=timezone.utc)
    summary = pipeline.run(
        client=client,
        since=since,
        dry_run=False,
        max_messages=50,
    )

    # Write run log
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
        return 0
    else:
        print("\nNo draft created (no qualifying listings or all filtered out).")
        return 0


if __name__ == "__main__":
    sys.exit(main())
