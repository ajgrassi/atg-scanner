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
    {
        "id": "19e22f9cb7d45fd3",
        "thread_id": "19e22f9cb7d45fd3",
        "sender": "skrepistman@sandsig.com",
        "subject": "Childcare Network - 246+ Unit Operator | 19+ Year NNN  | 2% Annual Increases | Valdosta, GA",
        "received_at": "2026-05-13T20:03:48Z",
        "text_body": """Sands Investment Group is pleased to exclusively offer for sale the 9,720 SF Childcare Network NNN Asset located at 275 Enterprise Drive in Valdosta, GA.

Childcare Network - Valdosta, GA

PRICE

$2,285,714


CAP RATE

7.00%

SQUARE FOOTAGE

9,720 SF

Investment Highlights

Founded in 1988, Childcare Network operates over 246 schools in the southern United States.
Positioned along the busy I-75 corridor between Atlanta and Tampa, the Valdosta attracts commuters and visitors from across Southern Georgia and North Florida.
Located 4 miles from Valdosta Regional Airport and 1.5 hours from Tallahassee International Airport (TLH).
19+ years remaining on a Triple Net (NNN) Lease with 2% annual rent escalations.
6 elementary feeder schools within a 5-mile radius.

Investment Advisors

Seth Krepistman
TX Lic. # 744270
512.543.7437
skrepistman@SandsIG.com
""",
    },
    {
        "id": "19e22baf938ab064",
        "thread_id": "19e22baf938ab064",
        "sender": "zboals@sandsig.com",
        "subject": "For Lease | Turnkey Medical Office | $11.75/SF | Established Patient Traffic",
        "received_at": "2026-05-13T19:03:56Z",
        "text_body": """Sands Investment Group is pleased to exclusively offer for lease the South Drive Medical Office at 117 South Drive in Natchitoches, LA 71457.

FOR LEASE — not for sale. No asking price. Skipping.
""",
    },
    {
        "id": "19e2288ebc7bfd36",
        "thread_id": "19e2288ebc7bfd36",
        "sender": "jliberatore@sandsig.com",
        "subject": "Just Exercised Option Period | White Castle | Corporate Guarantee | 7% Cap Rate | Columbus MSA",
        "received_at": "2026-05-13T18:03:48Z",
        "text_body": """Sands Investment Group is pleased to exclusively offer for sale the 2,200 SF White Castle Ground Lease located at 24599 US Highway 23 South in Circleville, Ohio, approximately 20 miles south of Columbus.

White Castle - Circleville, OH

PRICE

$628,000

CAP RATE

7.01%

SQUARE FOOTAGE

2,200 SF

Investment Highlights

Corporate Ground Lease Backed by White Castle: Guaranteed by White Castle System, Inc., a national QSR brand operating 345+ locations across 13 states.
Recently Exercised Option: White Castle recently exercised their option period, showing a strong continued commitment to this site and market.
3, 1-Year Options Remaining: White Castle has 3, 1-year option periods remaining, each starting July 1, with the potential to extend the lease through June 2030.
Proven Operating History Since 1999: White Castle has successfully operated at this location for over 25 years, demonstrating long-term commitment.
High-Traffic US-23 Location: Positioned directly on US Highway 23, a primary north-south retail corridor with 29,000+ vehicles per day.
Columbus MSA Location: Located approximately 20 miles south of Columbus.

Investment Advisors

Jack Liberatore
SC Lic. # 140365
jliberatore@SandsIG.com
""",
    },
    {
        "id": "19e224e5a76e627e",
        "thread_id": "19e224e5a76e627e",
        "sender": "tom@sandsig.com",
        "subject": "Just Listed | Acadia Healthcare (NASDAQ: ACHC) | 12+ Long-Term NNN | $18.58/ SF",
        "received_at": "2026-05-13T17:03:59Z",
        "text_body": """Sands Investment Group is pleased to present exclusively for sale the 8,346 SF Acadia Healthcare NNN Asset located at 175 Philpot Lane in Beckley, WV.

Acadia Healthcare - Beckley, WV

PRICE

$2,297,081

CAP RATE

6.75%

SQUARE FOOTAGE

8,346 SF

Investment Highlights

Acadia Healthcare (NASDAQ: ACHC) is a publicly traded behavioral healthcare company with an approximate market capitalization of $2.27 billion.
Beckley is the largest city in southern West Virginia and serves as a key economic and service hub for the surrounding Appalachian region.
Tenant has been in this location since 2016, operating under a grandfathered conditional use permit.

Investment Advisors

Tom Gorman
WV Lic. # WVB230300887
610.550.8884
tom@SandsIG.com
""",
    },
    {
        "id": "19e221c441bc29d1",
        "thread_id": "19e221c441bc29d1",
        "sender": "stratton@sandsig.com",
        "subject": "Rare Charleston NNN Industrial | 7% CAP Rate | 3% Annual Increases | North Charleston, SC",
        "received_at": "2026-05-13T16:03:50Z",
        "text_body": """Sands Investment Group is pleased to exclusively offer for sale the 19,500 SF Chugach Government Solutions NNN facility located at 7384-7392 Industry Drive in North Charleston, SC.

Chugach Government Solutions - North Charleston, SC

PRICE

$4,650,000

CAP RATE

7.02%

SQUARE FOOTAGE

19,500 SF

Investment Highlights

Strong Tenant: Chugach Government Solutions is one of the largest providers of construction, facilities management, technical, and education services supporting DoD and federal agencies worldwide.
Passive Lease Structure: Lease provides very limited landlord responsibilities and strong 3% annual rent escalations.
Recent Expansion: The tenant recently extended their lease early and expanded at the site.
Significant Tenant Investment: Over the years, the tenant has made significant capital investments in the building.

Investment Advisors

Stratton Greig
TX Lic. # 738303
512.910.2665
stratton@SandsIG.com
""",
    },
    {
        "id": "19e21e04ac62480d",
        "thread_id": "19e21e04ac62480d",
        "sender": "agilbert@sandsig.com",
        "subject": "Just Listed | Parker Chase Preschool of East Roswell - Alpharetta, GA | 100+ Unit Corporate Guarantee | Long-Term NNN",
        "received_at": "2026-05-13T15:04:00Z",
        "text_body": """Sands Investment Group is pleased to exclusively present for sale the 12,386 SF Parker-Chase Preschool Absolute NNN of East Roswell, located at 2852 Holcomb Bridge Road in Alpharetta, GA.

Parker-Chase Preschool of East Roswell - Alpharetta, GA

PRICE

$5,918,415

CAP RATE

6.75%

SQUARE FOOTAGE

12,386 SF

Investment Highlights

Corporately backed by Endeavor Schools, one of the fastest-growing early education brands in the country, with over 100 locations nationally since its founding in 2012.
This asset is 100% leased to Parker-Chase Preschool on an Absolute NNN Lease with ~14 years remaining, featuring 1.75% annual rental escalations and 4, 5-year renewal options.
Direct access to GA-400 enables seamless connectivity to major employment hubs.

Investment Advisors

Drew Gilbert
SC Lic. # 136866
843.212.9319
agilbert@SandsIG.com
""",
    },
    {
        "id": "19e21b21f6434acd",
        "thread_id": "19e21b21f6434acd",
        "sender": "dcoyle@sandsig.com",
        "subject": "Generational Grocery Asset | Recent Lease Extension & Major Renovations | Below-Market Financing",
        "received_at": "2026-05-13T14:03:52Z",
        "text_body": """Sands Investment Group is pleased to exclusively offer the 66,272 SF Stop & Shop NNN Asset located along the primary retail corridor connecting Main and Broad Streets.

Stop & Shop - Westfield, MA

PRICE

$9,327,170

CAP RATE

6.75%

SQUARE FOOTAGE

66,272 SF

Investment Highlights

Proven Grocer with 25-Year Track Record: Stop & Shop has successfully operated at this location since 2000, making it a true generational grocery asset.
Recent Lease Extension: The tenant exercised its renewal option in 2024, extending the lease through September 2030.
Investment-Grade Credit Backing: The lease is corporately guaranteed by Ahold Delhaize (BBB+/Baa1), one of the largest grocery operators in the world.
Premier Downtown Location: The site commands strong visibility in the heart of downtown Westfield.

Investment Advisors

Dan Coyle
TN Lic. # 382052
615.235.3548
dcoyle@SandsIG.com
""",
    },
    {
        "id": "19e2172682145df0",
        "thread_id": "19e2172682145df0",
        "sender": "zfriedman@sandsig.com",
        "subject": "Just Listed | Retail Development Site | ±32,000 SF - Lot can be Subdivided | High-Traffic | Georgia",
        "received_at": "2026-05-13T13:04:01Z",
        "text_body": """Sands Investment Group is pleased to exclusively offer for sale a Retail Center Development Asset opportunity located at 2984 Peachtree Parkway in Suwanee, GA.

Retail Center Development - Suwanee, GA

PRICE

Lot Can Be Subdivided - Contact Broker For Pricing

Investment Highlights

Approved site plans for a +/- 32,000 SF anchor tenants and six individual lots with Peachtree Parkway frontage.
46,400 VPD along +/- 1,300 linear feet of frontage on Peachtree Parkway.
Zoned CBD allowing retail, restaurant, bank, daycare, service, and office use.
Future traffic light at Bagley Drive & Peachtree Parkway for controlled access.
Publix Plaza and Target & Home Depot Center are within a half-mile.

Investment Advisors

Zach Friedman
FL Lic. # SL3643776
954.902.5256
zfriedman@SandsIG.com
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
    "19e22f9cb7d45fd3": {
        "Sale Price": "$2,285,714",
        "Cap Rate": "7.00%",
        "Building Size": "9720 SF",
        "Tenant": "Childcare Network",
        "Lease Type": "NNN",
        "Rent Escalator": "2%",
        "Lease Term": "19 years",
    },
    "19e2288ebc7bfd36": {
        "Sale Price": "$628,000",
        "Cap Rate": "7.01%",
        "Building Size": "2200 SF",
        "Tenant": "White Castle",
        "Lease Type": "Ground Lease",
    },
    "19e224e5a76e627e": {
        "Sale Price": "$2,297,081",
        "Cap Rate": "6.75%",
        "Building Size": "8346 SF",
        "Tenant": "Acadia Healthcare",
        "Lease Type": "NNN",
    },
    "19e221c441bc29d1": {
        "Sale Price": "$4,650,000",
        "Cap Rate": "7.02%",
        "Building Size": "19500 SF",
        "Tenant": "Chugach Government Solutions",
        "Lease Type": "NNN",
        "Rent Escalator": "3%",
    },
    "19e21e04ac62480d": {
        "Sale Price": "$5,918,415",
        "Cap Rate": "6.75%",
        "Building Size": "12386 SF",
        "Tenant": "Parker-Chase Preschool",
        "Lease Type": "Absolute NNN",
        "Rent Escalator": "1.75%",
        "Lease Term": "14 years",
    },
    "19e21b21f6434acd": {
        "Sale Price": "$9,327,170",
        "Cap Rate": "6.75%",
        "Building Size": "66272 SF",
        "Tenant": "Stop & Shop",
        "Lease Type": "NNN",
    },
    # 19e22baf938ab064 (For Lease — skip) and 19e2172682145df0 (no price) omitted
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

    since = datetime(2026, 5, 13, 0, 0, 0, tzinfo=timezone.utc)
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
