"""End-to-end ingestion pipeline.

Stitches together:
  Gmail search → resolve parser → parse → dedup → score → persist → digest.

The pipeline accepts a `GmailClient` (real or fake) so we can test the
full flow without hitting Gmail.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import asdict
from datetime import datetime
from typing import Any, Iterable

from .config import (
    SAVED_SEARCH_TO_CHANNEL,
    SOURCES,
    gmail_from_query,
    resolve_source,
)
from .db import _json, transaction
from .deduper import find_duplicate
from .digest import (
    Digest,
    DigestRow,
    PriceDropRow,
    ScanStats,
    build_draft,
)
from .gmail_client import DraftRequest, EmailMessage, GmailClient
from .listing import Listing, ScoreResult
from .parsers.base import Parser
from .scorers import get_scorer
from .utils import get_logger, utc_now

log = get_logger("pipeline")


# ----------------------------------------------------------------- parsers

_PARSER_CACHE: dict[str, Parser] = {}


def _load_parser(parser_name: str) -> Parser:
    """Load a parser module + instantiate its single Parser-subclass.

    Caches the instance; parsers are stateless and cheap to reuse.
    """
    if parser_name in _PARSER_CACHE:
        return _PARSER_CACHE[parser_name]
    mod = importlib.import_module(f"app.parsers.{parser_name}")
    cls: type[Parser] | None = next(
        (v for v in vars(mod).values()
         if isinstance(v, type) and issubclass(v, Parser) and v is not Parser
         and v.__module__ == mod.__name__),
        None,
    )
    if cls is None:
        raise RuntimeError(f"app.parsers.{parser_name} has no Parser subclass")
    inst = cls()
    _PARSER_CACHE[parser_name] = inst
    return inst


# ----------------------------------------------------------------- run

def run(
    *,
    client: GmailClient,
    since: datetime,
    dry_run: bool = False,
    max_messages: int = 200,
) -> dict[str, Any]:
    """Run one ingestion pass.

    Returns a summary dict (also written to run_log.json by the caller).
    """
    query = f"{gmail_from_query()} after:{int(since.timestamp())}"
    log.info("pipeline.start", query=query, dry_run=dry_run)

    messages = client.search(query, max_results=max_messages) or []

    sources_active: set[str] = set()
    sources_failed: list[str] = []
    parser_failures: list[dict[str, Any]] = []
    new_count = 0
    updated_count = 0
    score_rows: list[DigestRow] = []
    price_drops: list[PriceDropRow] = []

    for msg in messages:
        resolved = resolve_source(msg.sender)
        if resolved is None:
            log.debug("pipeline.unmatched_sender", sender=msg.sender, subject=msg.subject)
            continue
        _channels, parser_name = resolved
        try:
            parser = _load_parser(parser_name)
        except Exception as e:                              # noqa: BLE001
            sources_failed.append(parser_name)
            parser_failures.append({"parser": parser_name, "error": str(e),
                                    "msg": msg.id})
            continue

        try:
            result = parser.parse(msg)
        except Exception as e:                              # noqa: BLE001
            sources_failed.append(parser_name)
            parser_failures.append({"parser": parser_name, "error": str(e),
                                    "msg": msg.id})
            continue

        sources_active.add(parser_name)
        for warning in result.warnings:
            log.debug("pipeline.parser.warning", parser=parser_name, warning=warning)

        for listing in result.listings:
            persisted_id, change = _persist_and_score(listing)
            if persisted_id is None:
                continue
            if change == "new":
                new_count += 1
            elif change == "updated":
                updated_count += 1
                if change_drop := change == "updated_price_drop":
                    pass

            # Score for the digest payload.
            try:
                score = get_scorer(listing.channel).evaluate(listing)
            except Exception as e:                          # noqa: BLE001
                log.warning("pipeline.score_failed",
                            channel=listing.channel, error=str(e))
                continue

            if score.verdict == "STRUCTURAL_FAIL":
                continue

            score_rows.append(DigestRow(
                listing=listing, score=score.score, verdict=score.verdict,
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
            emails_processed=len(messages),
            listings_found=len(score_rows),
            listings_new=new_count,
            listings_updated=updated_count,
            sources_active=sorted(sources_active),
            sources_failed=sorted(set(sources_failed)),
        ),
    )

    draft_id: str | None = None
    if not dry_run:
        draft = build_draft(digest)
        if draft is not None:
            draft_id = client.create_draft(draft)

    return {
        "started_at": digest.generated_at.isoformat(),
        "phase": "3_pipeline",
        "dry_run": dry_run,
        "since": since.isoformat(),
        "gmail_query": query,
        "emails_processed": digest.stats.emails_processed,
        "listings_found": digest.stats.listings_found,
        "listings_new": digest.stats.listings_new,
        "listings_updated": digest.stats.listings_updated,
        "parser_failures": parser_failures,
        "draft_created": bool(draft_id),
        "draft_id": draft_id,
        "sources_active": digest.stats.sources_active,
        "sources_failed": digest.stats.sources_failed,
    }


# ----------------------------------------------------------------- helpers

def _top3(components: dict[str, float]) -> list[tuple[str, float]]:
    return sorted(components.items(), key=lambda kv: kv[1], reverse=True)[:3]


def _persist_and_score(listing: Listing) -> tuple[int | None, str]:
    """Insert or update the listing in SQLite. Returns (id, change_kind)."""
    now = utc_now()
    listing.first_seen = listing.first_seen or now
    listing.last_seen = now

    with transaction() as conn:
        dup = find_duplicate(conn, listing)

        if dup.is_duplicate and dup.existing_listing_id is not None:
            # Update last_seen, log a price-change event if applicable.
            conn.execute(
                "UPDATE listings SET last_seen = ?, price = ? WHERE id = ?",
                (now.isoformat(), listing.price, dup.existing_listing_id),
            )
            if dup.price_changed_pct and abs(dup.price_changed_pct) > 0.02:
                conn.execute(
                    "INSERT INTO listing_events "
                    "(listing_id, event_type, occurred_at, details_json) "
                    "VALUES (?, 'price_change', ?, ?)",
                    (dup.existing_listing_id, now.isoformat(),
                     json.dumps({
                         "previous_price": dup.previous_price,
                         "new_price": listing.price,
                         "pct": dup.price_changed_pct,
                     })),
                )
            return dup.existing_listing_id, "updated"

        # Insert new
        cur = conn.execute(
            """
            INSERT INTO listings
              (source, source_listing_id, channel, listing_url, email_id,
               title, address, city, state, zip,
               price, cap_rate, noi, sf, lot_acres,
               tenant, tenant_credit, lease_type, lease_start, lease_expiration,
               term_remaining_years, escalator_pct, roof_structure,
               bonus_dep_eligible, estimated_cost_seg_pct,
               extraction_confidence, needs_review, raw_data_json,
               first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?)
            """,
            (
                listing.source, listing.source_listing_id, listing.channel,
                listing.listing_url, listing.email_id,
                listing.title, listing.address, listing.city, listing.state, listing.zip,
                listing.price, listing.cap_rate, listing.noi, listing.sf, listing.lot_acres,
                listing.tenant, listing.tenant_credit, listing.lease_type,
                listing.lease_start.isoformat() if listing.lease_start else None,
                listing.lease_expiration.isoformat() if listing.lease_expiration else None,
                listing.term_remaining_years, listing.escalator_pct, listing.roof_structure,
                int(listing.bonus_dep_eligible) if listing.bonus_dep_eligible is not None else None,
                listing.estimated_cost_seg_pct,
                listing.extraction_confidence, int(listing.needs_review),
                _json(listing.raw_data),
                listing.first_seen.isoformat() if listing.first_seen else None,
                listing.last_seen.isoformat() if listing.last_seen else None,
            ),
        )
        return int(cur.lastrowid), "new"
