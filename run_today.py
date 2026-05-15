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

EMAILS: list[dict] = [
    # ── 2026-05-14 batch (fetched live from Gmail MCP) ────────────────────
    {
        "id": "19e281d3e50bba3d",
        "thread_id": "19e281d3e50bba3d",
        "sender": "max@sandsig.com",
        "subject": "Corporate-Backed KinderCare | Minneapolis MSA | 2% Annual Increases",
        "received_at": "2026-05-14T20:03:44Z",
        "text_body": """We are pleased to exclusively offer for sale the 11,990 SF KinderCare NNN Asset located at 4025 Benjamin Drive in Minneapolis, MN.

KinderCare - Minneapolis, MN

PRICE

$5,575,881

CAP RATE

6.75%

SQUARE FOOTAGE

11,990 SF

Investment Highlights

KinderCare is the largest provider of early education and child care, operating more than 2,700 centers nationwide.
Minneapolis forms the "Twin Cities" region, combined with Saint Paul, and is the most populous city in the state.
15 miles from Minneapolis-Saint Paul International Airport (MSP).
Average household income of $161,697 and a population of 57,861 residents within a 3-mile radius.
9 elementary feeder schools within a 5-mile radius.

Investment Advisors

Max Freedman
TX Lic. # 644481
512.766.2711
max@SandsIG.com
""",
    },
    {
        "id": "19e27e280d90623a",
        "thread_id": "19e27e280d90623a",
        "sender": "cmartino@sandsig.com",
        "subject": "Just Listed | 2-Unit Car Wash Portfolio | Detroit MSA | Strong Cash Flow | Below Replacement Cost",
        "received_at": "2026-05-14T19:03:54Z",
        "text_body": """Sands Investment Group is pleased to exclusively offer for sale the Imperial Car Wash Portfolio, comprising of 2 operational car wash facilities in Waterford Township, MI.

Imperial Car Wash Portfolio - Waterford Township, MI

PRICE

$5,000,000

SQUARE FOOTAGE

11,211 SF

Investment Highlights

Priced Below Replacement Cost with In-Place Cash Flow: Both sites are operational and revenue-generating with newly installed equipment, offered at a meaningful discount to estimated replacement cost.
Hard Barrier to New Competition: Waterford Township maintains an active moratorium on new car wash development, directly protecting both sites from new supply within the trade area.
Major Redevelopment Tailwind at Site 1: Site 1 fronts the 74-acre Oakland County Business Center, a $63M mixed-use redevelopment of the former Summit Place Mall.
High-Traffic, High-Visibility Corridors: Site 1 sits on Elizabeth Lake Road. Site 2 fronts M-59. Combined exposure to approximately 40,000 VPD.

Investment Advisors

Chase Martino
CA Lic. # 02309579
310.241.3677
cmartino@SandsIG.com
""",
    },
    {
        "id": "19e27b17efc45ac0",
        "thread_id": "19e27b17efc45ac0",
        "sender": "jmulloy@sandsig.com",
        "subject": "New Concept | Boost Coffee - ABS NNN | Corporate + Personal Guarantee | Jacksonville, FL",
        "received_at": "2026-05-14T18:03:49Z",
        "text_body": """Sands Investment Group is pleased to exclusively present for sale the Boost Coffee Absolute NNN Ground Lease property located at 7253 103rd Street in Jacksonville, FL.

Boost Coffee - Jacksonville, FL

PRICE

$1,950,000

CAP RATE

6.46%

SQUARE FOOTAGE

790 SF

Investment Highlights

Long-Term 15-Year ABS NNN Ground Lease (Zero Landlord Responsibilities): This is a true passive investment featuring a 15-Year Absolute NNN Ground Lease.
Attractive Rent Escalations & Inflation Hedge: 10% rent increases every 5 years throughout the primary 15-year term.
Corporate Guarantee From Proven Operators: The lease is backed by a corporate guarantee.
15 years remaining on lease.

Investment Advisors

Jordan Mulloy
TX Lic. # 793071
512.768.0380
jmulloy@SandsIG.com
""",
    },
    {
        "id": "19e2775ce24807a6",
        "thread_id": "19e2775ce24807a6",
        "sender": "agilbert@sandsig.com",
        "subject": "New Listing | Ladybird Academy - Orlando, FL | Corporate & Personal Guarantee | 11+ Years Abs. NNN",
        "received_at": "2026-05-14T17:03:53Z",
        "text_body": """Sands Investment Group is pleased to present exclusively for sale the 11,732 SF KinderCare Absolute NNN Asset located at 8730 Nesbit Ferry Road in Alpharetta, GA.

Ladybird Academy - Orlando, FL

PRICE

$7,142,576

CAP RATE

6.75%

SQUARE FOOTAGE

12,184 SF

Investment Highlights

This location is a rare, corporately operated Ladybird Academy. Ladybird Academy operates 22+ locations throughout Florida and has been in business since 2002.
This asset is 100% leased to Ladybird Academy on an Absolute Triple Net (NNN) Lease with 11+ years remaining, featuring above-market annual rental escalations and two rare 10-year renewal options.
Total consumer spending on education and daycare exceeds $100 million annually within a 5-mile radius.

Investment Advisors

Drew Gilbert
SC Lic. # 136866
843.212.9319
agilbert@SandsIG.com
""",
    },
    {
        "id": "19e271f88bf2baff",
        "thread_id": "19e271f88bf2baff",
        "sender": "info@sandsig.com",
        "subject": "Last Chance to Book a Meeting with SIG at ICSC Las Vegas",
        "received_at": "2026-05-14T15:33:58Z",
        "text_body": """Andrew, let's make in person deals happen!

Come meet the SIG team at ICSC Las Vegas. Book a meeting today.

Sands Investment Group
""",
    },
    {
        "id": "19e27074d5020b94",
        "thread_id": "19e27074d5020b94",
        "sender": "mcoleman@sandsig.com",
        "subject": "Just Listed | Bojangles - Columbia, SC | Corporate Guarantee | 108K+ VPD | 30 Years of Operational History",
        "received_at": "2026-05-14T15:04:06Z",
        "text_body": """Sands Investment Group is pleased to exclusively present for sale the 4,236 SF Bojangles Absolute NNN Asset located at 2423 Broad River Road in Columbia, SC.

Bojangles - Columbia, SC

PRICE

$2,549,089

CAP RATE

6.15%

SQUARE FOOTAGE

4,236 SF

Investment Highlights

6+ years remaining on an Absolute NNN Lease with 8% increases at each 3 x 5-year option.
Restaurant has operated at this location for more than 30 years.
Strong corporate guarantee from one of the leading brands in chicken QSR, with over 800 units and growing.
Located directly along Broad River Road, which sees over 38,600 vehicles per day.
Less than 1 mile from Interstate 20 with over 108,000 VPD.

Investment Advisors

Mitchell Coleman
GA Lic. # 444363
843.931.9580
mcoleman@SandsIG.com
""",
    },
    {
        "id": "19e26d3d1bbfaacd",
        "thread_id": "19e26d3d1bbfaacd",
        "sender": "bpugh@sandsig.com",
        "subject": "7.13% Cap Rate | 3% Annual Rent Increases | 9 Years of Term Remaining",
        "received_at": "2026-05-14T14:03:48Z",
        "text_body": """Sands Investment Group is pleased to exclusively offer for sale the 24,550 SF Joe Hudson's Collision Center and Baker's Towing & Recovery located at 3327 & 3407 S Lake Drive in Texarkana, Texas.

Gerber Collision & Glass and Baker's Towing - Texarkana, TX

PRICE

$3,173,000

CAP RATE

7.13%

SQUARE FOOTAGE

24,550 SF

Investment Highlights

Strong Anchor Tenant Net Lease: Collision center occupied by Gerber Collision & Glass, a multi-location national collision repair operator with 1300+ locations. Gerber operates under The Boyd Group Services Inc. (BGSI).
Baker's Towing & Recovery: Baker's Towing operates one of the most comprehensive heavy-duty fleets in the Texarkana region.
Double Net (NN) Leases: Minimal landlord responsibilities with stable in-place income across both.
9 years of term remaining across both leases with 3% annual rent increases.
Prime Automotive Corridor: Located along S Lake Drive (State Highway 93).

Investment Advisors

Bryce Pugh
NC Lic. # 347566
704.912.5085
bpugh@SandsIG.com
""",
    },
    {
        "id": "19e269bc50e3d684",
        "thread_id": "19e269bc50e3d684",
        "sender": "hkirby@sandsig.com",
        "subject": "Just Listed | National Credit Tenant - White Cap | 550+ Locations | 7.67% CAP",
        "received_at": "2026-05-14T13:03:56Z",
        "text_body": """Sands Investment Group is pleased to exclusively offer for sale the White Cap Industrial NNN Asset located in Flint, MI.

White Cap (Colony Hardware) - Flint, MI

PRICE

$900,000

CAP RATE

7.67%

SQUARE FOOTAGE

12,300 SF

Investment Highlights

National Credit Tenant: White Cap is one of the largest distributors of building materials, specialty construction supplies, and safety products in North America, with over 550+ locations.
Strategic Acquisition: White Cap officially acquired Colony Hardware to expand its geographic footprint in the Northeast, Midwest, and Florida.
Strategically Located: This facility is located right off Robert T Longway Boulevard (which sees over 14,000 vehicles per day), highly accessible to I-475.
Healthy Rent: This asset features slightly under-market rent, presenting potential future upside for investors.

Investment Advisors

Hunter Kirby
TX Lic. # 843738
512.856.7596
hkirby@SandsIG.com
""",
    },
]

# ── Inject canonical fields known from the email body ─────────────────────
# The generic parser needs LABEL: value pairs. The Sands IG blasts use a
# two-line format (label then value on separate lines).  We patch the text
# body here to inject colon-separated KV lines that the parser can pick up,
# preserving all original content.

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
    # 2026-05-14 batch
    "19e281d3e50bba3d": {
        "Sale Price": "$5,575,881",
        "Cap Rate": "6.75%",
        "Building Size": "11990 SF",
        "Tenant": "KinderCare",
        "Lease Type": "NNN",
        "Rent Escalator": "2%",
    },
    "19e27e280d90623a": {
        "Sale Price": "$5,000,000",
        "Building Size": "11211 SF",
        "Tenant": "Imperial Car Wash",
        "Lease Type": "None",
    },
    "19e27b17efc45ac0": {
        "Sale Price": "$1,950,000",
        "Cap Rate": "6.46%",
        "Building Size": "790 SF",
        "Tenant": "Boost Coffee",
        "Lease Type": "Ground Lease",
        "Lease Term": "15 years",
    },
    "19e2775ce24807a6": {
        "Sale Price": "$7,142,576",
        "Cap Rate": "6.75%",
        "Building Size": "12184 SF",
        "Tenant": "Ladybird Academy",
        "Lease Type": "Absolute NNN",
        "Lease Term": "11 years",
    },
    # 19e271f88bf2baff: ICSC marketing event email — no listing
    "19e27074d5020b94": {
        "Sale Price": "$2,549,089",
        "Cap Rate": "6.15%",
        "Building Size": "4236 SF",
        "Tenant": "Bojangles",
        "Lease Type": "Absolute NNN",
        "Lease Term": "6 years",
    },
    "19e26d3d1bbfaacd": {
        "Sale Price": "$3,173,000",
        "Cap Rate": "7.13%",
        "Building Size": "24550 SF",
        "Tenant": "Gerber Collision & Glass / Baker's Towing",
        "Lease Type": "NN",
        "Lease Term": "9 years",
        "Rent Escalator": "3%",
    },
    "19e269bc50e3d684": {
        "Sale Price": "$900,000",
        "Cap Rate": "7.67%",
        "Building Size": "12300 SF",
        "Tenant": "White Cap",
        "Lease Type": "NNN",
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

    messages = build_messages()
    client = PreloadedGmailClient(messages, draft_out)

    since = datetime(2026, 5, 14, 0, 0, 0, tzinfo=timezone.utc)
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
