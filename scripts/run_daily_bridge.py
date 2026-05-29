"""Bridge script: convert Gmail MCP thread data → pipeline EmailMessage objects → run full scan."""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import db
from app.digest import build_draft
from app.gmail_client import Attachment, DraftRequest, EmailMessage
from app.listing import Listing
from app.pipeline import _persist_and_score, _top3
from app.parsers.sands_ig import SandsIgParser
from app.digest import Digest, DigestRow, PriceDropRow, ScanStats
from app.scorers import get_scorer
from app.utils import utc_now, get_logger, configure_logging

configure_logging()
log = get_logger("bridge")


# Raw email data captured from Gmail MCP (6 Sands IG emails + 1 capital markets)
EMAILS = [
    {
        "id": "19e6fcb636a703f2",
        "thread_id": "19e6fcb636a703f2",
        "sender": "jmulloy@sandsig.com",
        "subject": "Austin, TX | ABS NNN | 7.00% CAP Korean BBQ | New 10-Year Lease | Off I-35 (200K+ VPD)",
        "received_at": "2026-05-28T18:03:42Z",
    },
    {
        "id": "19e6f8cdf70fa930",
        "thread_id": "19e6f8cdf70fa930",
        "sender": "jbartlett@sandsig.com",
        "subject": "New Listing | Hard-Corner Gas Station | 7.50% CAP | Experienced Operator | 17 Years Remaining",
        "received_at": "2026-05-28T17:03:56Z",
    },
    {
        "id": "19e6f5d722140781",
        "thread_id": "19e6f5d722140781",
        "sender": "agilbert@sandsig.com",
        "subject": "Children's Courtyard | Absolute NNN | 6.75% Cap Rate",
        "received_at": "2026-05-28T16:03:52Z",
    },
    {
        "id": "19e6f1f2520dceaa",
        "thread_id": "19e6f1f2520dceaa",
        "sender": "dave@sandsig.com",
        "subject": "New Listing | Vacant QSR Site | High Visibility | I-10 Corridor | Large Mixed-Use Development",
        "received_at": "2026-05-28T15:03:50Z",
    },
    {
        "id": "19e6eee7f38e3d68",
        "thread_id": "19e6eee7f38e3d68",
        "sender": "jliberatore@sandsig.com",
        "subject": "8.00% CAP | Advance Auto Parts | Corporate Guarantee | Alabama",
        "received_at": "2026-05-28T14:03:48Z",
    },
    {
        "id": "19e6eb46c9244c5b",
        "thread_id": "19e6eb46c9244c5b",
        "sender": "clifton@sandsig.com",
        "subject": "New Listing | Abs. NNN Sale Leaseback | Guaranteed Buyout | Corporate Guarantee | Depreciable Asset",
        "received_at": "2026-05-28T13:03:49Z",
    },
    # Capital markets update — not a listing
    {
        "id": "19e6fdd1478ebe23",
        "thread_id": "19e6fdd1478ebe23",
        "sender": "info@sandsig.com",
        "subject": "SIG Capital Markets | Treasury Yields Climb Above 4%",
        "received_at": "2026-05-28T18:33:40Z",
        "text_body": "",  # no listing, skip
    },
]

# Text bodies extracted from HTML (since emails are HTML-only)
TEXT_BODIES = {
    "19e6fcb636a703f2": """
Sands Investment Group is pleased to exclusively offer for sale the 6,324 SF DAM-A Korean Hotpot & BBQ NN located at 713 E Huntland Drive in Austin, Texas.

DAM-A Korean Hotpot & BBQ - Austin, TX

PRICE
$4,000,000

CAP RATE
7.00%

SQUARE FOOTAGE
6,324 SF

Investment Highlights

Long-Term 10-Year Sale-Leaseback:
The property features a brand new 10-year lease term upon closing, providing an investor with long-term passive cash flow.

Absolute Triple Net (NNN) Lease with Zero Landlord Responsibilities:
This is an Absolute Triple Net (NNN) Lease where the landlord has zero responsibilities. Offering a hands-off investment for a passive owner.

Significant Tenant Investment in Property:
The tenant has invested approximately $500,000 in renovations, demonstrating a strong commitment to this location and its long-term success.

Hedge Against Inflation with Attractive Rent Increases:
The lease features 10% rental increases every five years, providing a strong hedge against inflation and consistent growth in returns.

Investment Advisors
Jordan Mulloy
TX Lic. # 793071
512.768.0380
jmulloy@SandsIG.com
""",
    "19e6f8cdf70fa930": """
Sands Investment Group is pleased to exclusively offer for sale the 3,214 SF Chisholm Corner Gas Station located at 601 OK-19 in Alex, OK.

Chisholm Corner Gas Station - Alex, OK

PRICE
$2,099,587

CAP RATE
7.50%

SQUARE FOOTAGE
3,214 SF

Investment Highlights

~17-Year Absolute Triple Net (NNN) Lease:
Structured with zero landlord responsibilities, offering passive and predictable income for ownership.

Experienced Operator:
Operated by Diamond Jubilee Oil, LLC under a master lease assigned in February 2026.

Two-Tier Guaranty Structure:
Backed by City Mart Energy LLC, an experienced regional fuel wholesaler, in addition to a personal guaranty from the owner of Diamond Jubilee Oil, LLC.

Long Operating History & Renewed Commitment:
The tenant has successfully operated at this location for years and recently executed a new lease

Investment Advisors
Jeremy Bartlett
TX Lic. # 847818-SA
512.885.3634
jbartlett@SandsIG.com
""",
    "19e6f5d722140781": """
Sands Investment Group is Pleased to Exclusively Offer For Sale the 15,437 SF The Children's Courtyard Absolute NNN Located at 7666 Wallace Rd in Orlando, FL.

The Children's Courtyard - Orlando, FL

PRICE
$4,622,222

CAP RATE
6.75%

SQUARE FOOTAGE
15,437 SF

Investment Highlights

This Asset is 100% Leased to The Children's Courtyard on an Absolute Triple Net (NNN) Lease With Zero Landlord Responsibilities - 11.5 Years of Term Remaining

Corporately Backed By Learning Care Group, Inc., Which is the 2nd Largest For-Profit Childcare Company in North America and a Leader in Early Education, With a Network of Over 1,150 Locations in the Country, With a Capacity For Over 156,000 Students and 11+ Brands

Total Consumer Spending on Education and Daycare Exceeds $144 Million Annually Within a 5-Mile Radius of This Location, and Average Household Income Exceeds $144,124 Within a 1-Mile Radius of This Location

Investment Advisors
Drew Gilbert
SC Lic. # 136866
843.212.9319
agilbert@SandsIG.com
""",
    "19e6f1f2520dceaa": """
Sands Investment Group is pleased to exclusively offer for sale the 2,300 SF Vacant Del Taco Asset property located at 2760 US-331 in DeFuniak Springs, Florida.

Vacant Del Taco - DeFuniak Springs, FL

PRICE
$1,800,000

SQUARE FOOTAGE
2,300 SF

Investment Highlights

2024 construction drive-thru QSR positioned along the primary north/south corridor connecting Interstate 10 to Florida's Emerald Coast beaches via US-331.

Excellent opportunity for a developer with tenant relationships or an owner/user seeking second-generation drive-thru infrastructure in a rapidly expanding retail node.

Investment Advisors
Dave Wirgler
TX Lic. # 839305
512.402.3395
dave@SandsIG.com
""",
    "19e6eee7f38e3d68": """
Sands Investment Group is Pleased to Exclusively Offer For Sale the 7,000 SF Advance Auto Parts Located at 111 N McCurdy Ave in Rainsville, AL.

Advance Auto Parts - Rainsville, AL

PRICE
$1,530,006

CAP RATE
8.00%

SQUARE FOOTAGE
7,000 SF

Investment Highlights

The lease is backed by Advance Auto Parts, a company with an investment-grade credit rating of BB+ from S&P and Ba1 from Moody's, and $9.1 billion in annual sales for 2024.

Within a 3-mile radius, Rainsville features a demographic profile hosting 6,248 residents with an average household income of $67,550.

Premier leader in the automotive aftermarket parts industry with over 4,200 stores in operation.

Founded in 1932, Advance Auto Parts employs over 69,000 people nationwide.

Publicly traded entity on the New York Stock Exchange (NYSE: AAP).

Investment Advisors
Jack Liberatore
SC Lic. # 140365
843.510.0551
jliberatore@SandsIG.com
""",
    "19e6eb46c9244c5b": """
Sands Investment Group is pleased to exclusively present a high-yield, net lease investment opportunity in VENU FireSuites - fully managed, premium condo-style entertainment suites located within five world-class VENU venues.

VENU FireSuites | Premium Condo-Style Entertainment Suites

PRICE
$240K-1.2M

CAP RATE
11.00%

LEASE TYPE
Absolute NNN

Investment Highlights

Hands-Free Ownership:
Absolute NNN lease requires zero landlord responsibilities.

Long-Term Stability:
15-year primary term. (Option for 5 and 10-year terms available)

Guaranteed Buyout Option:
Available at years 5, 10, and 15

Built-In Depreciation Benefits:
Potential to capture up to 50% depreciation in year one, with the remaining basis depreciated over time. Consult your CPA.

High Cash Flow:
11.00% CAP rate with 2% annual rent escalation.

Corporate Credit:
Backed by VENU Holding Corporation.

Investment Advisors
Clifton McCrory
SC Lic. # 99847
540.255.5496
clifton@SandsIG.com
""",
}

BROKER_CONTACTS = {
    "19e6fcb636a703f2": "Jordan Mulloy — jmulloy@SandsIG.com — 512.768.0380",
    "19e6f8cdf70fa930": "Jeremy Bartlett — jbartlett@SandsIG.com — 512.885.3634",
    "19e6f5d722140781": "Drew Gilbert — agilbert@SandsIG.com — 843.212.9319",
    "19e6f1f2520dceaa": "Dave Wirgler — dave@SandsIG.com — 512.402.3395",
    "19e6eee7f38e3d68": "Jack Liberatore — jliberatore@SandsIG.com — 843.510.0551",
    "19e6eb46c9244c5b": "Clifton McCrory — clifton@SandsIG.com — 540.255.5496",
}


def main() -> dict:
    db.migrate()
    parser = SandsIgParser()

    emails_processed = 0
    listings_found = 0
    listings_new = 0
    listings_updated = 0
    parser_failures: list[dict] = []
    sources_active: set[str] = set()
    score_rows: list[DigestRow] = []
    price_drops: list[PriceDropRow] = []

    for email_meta in EMAILS:
        msg_id = email_meta["id"]
        text_body = TEXT_BODIES.get(msg_id, "")

        # Skip capital markets / non-listing blasts
        if not text_body.strip():
            log.info("bridge.skip_no_body", id=msg_id, subject=email_meta["subject"])
            continue

        msg = EmailMessage(
            id=msg_id,
            thread_id=email_meta["thread_id"],
            sender=email_meta["sender"],
            subject=email_meta["subject"],
            received_at=email_meta["received_at"],
            text_body=text_body,
            html_body=None,
            attachments=[],
        )

        emails_processed += 1

        try:
            result = parser.parse(msg)
        except Exception as e:
            parser_failures.append({"parser": "sands_ig", "error": str(e), "msg": msg_id})
            log.warning("bridge.parse_error", id=msg_id, error=str(e))
            continue

        sources_active.add("sands_ig")

        for warning in result.warnings:
            log.info("bridge.warning", warning=warning)

        for listing in result.listings:
            listings_found += 1
            # Store broker contact in raw_data for digest
            listing.raw_data["broker_contact"] = BROKER_CONTACTS.get(msg_id, "")

            persisted_id, change = _persist_and_score(listing)
            if persisted_id is None:
                continue
            if change == "new":
                listings_new += 1
            elif change in ("updated", "updated_price_drop"):
                listings_updated += 1

            try:
                scorer = get_scorer(listing.channel)
                gates_ok, failed_gates = scorer.structural_gates(listing)
                if not gates_ok:
                    log.info(
                        "bridge.structural_fail",
                        title=listing.title,
                        channel=listing.channel,
                        failed=failed_gates,
                    )
                    continue
                score = scorer.score(listing)
            except Exception as e:
                log.warning("bridge.score_error", channel=listing.channel, error=str(e))
                continue

            score_rows.append(DigestRow(
                listing=listing,
                score=score.score,
                verdict=score.verdict,
                components_top3=_top3(score.components),
            ))

    score_rows.sort(key=lambda r: r.score, reverse=True)
    by_channel: dict[str, list[DigestRow]] = {}
    for r in score_rows:
        by_channel.setdefault(r.listing.channel, []).append(r)

    digest = Digest(
        generated_at=utc_now(),
        overall_top10=score_rows[:10],
        by_channel=by_channel,
        price_drops=price_drops,
        stats=ScanStats(
            emails_processed=emails_processed,
            listings_found=listings_found,
            listings_new=listings_new,
            listings_updated=listings_updated,
            sources_active=sorted(sources_active),
            sources_failed=[f["parser"] for f in parser_failures],
        ),
    )

    # Print what we have
    print(f"\n{'='*60}")
    print("PIPELINE SUMMARY")
    print(f"{'='*60}")
    print(f"Emails processed: {emails_processed}")
    print(f"Listings found (parsed): {listings_found}")
    print(f"Listings new: {listings_new}")
    print(f"Listings updated: {listings_updated}")
    print(f"Passed structural gates: {len(score_rows)}")
    print(f"Parser failures: {len(parser_failures)}")
    if parser_failures:
        for f in parser_failures:
            print(f"  - {f}")
    print()

    if score_rows:
        print("SCORED LISTINGS (passed structural gates):")
        for r in score_rows:
            print(f"  [{r.verdict} {r.score:.0f}] {r.listing.title}")
            print(f"    {r.listing.address} | ${r.listing.price:,} | cap={r.listing.cap_rate}")
            print(f"    Top components: {r.components_top3}")
    else:
        print("No listings passed structural gates today.")

    draft = build_draft(digest)
    if draft is None:
        print("\nNo draft created (no new listings, no price drops).")
        return {
            "digest": digest,
            "draft": None,
            "score_rows": score_rows,
            "listings_new": listings_new,
            "listings_found": listings_found,
            "emails_processed": emails_processed,
        }

    print(f"\nDRAFT SUBJECT: {draft.subject}")
    print(f"DRAFT BODY (first 500 chars):\n{draft.html_body[:500]}")

    return {
        "digest": digest,
        "draft": draft,
        "score_rows": score_rows,
        "listings_new": listings_new,
        "listings_found": listings_found,
        "emails_processed": emails_processed,
    }


if __name__ == "__main__":
    result = main()
    # Save draft body for inspection
    if result["draft"]:
        Path("data/draft_preview.html").write_text(result["draft"].html_body)
        print("\nFull draft saved to data/draft_preview.html")
    # Save run summary
    import json
    summary = {
        "emails_processed": result["emails_processed"],
        "listings_found": result["listings_found"],
        "listings_new": result["listings_new"],
        "score_rows": len(result["score_rows"]),
    }
    print(f"\nSummary: {json.dumps(summary, indent=2)}")
