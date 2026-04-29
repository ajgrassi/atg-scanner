"""Listing dedup logic — three rules per CLAUDE.md § DEDUP LOGIC.

Strategy:
1. Exact: same (source, source_listing_id) → DUPLICATE.
2. Address-based: address Levenshtein ≤ 5 AND price within 2% → DUPLICATE.
3. Tenant-based (NNN): same tenant + address Lev ≤ 10 + price within 5% → DUPLICATE.

Returns a small DedupResult with the matched-listing-id (if any) plus a
flag for whether the price changed enough to warrant a price-drop alert.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Any

from rapidfuzz.distance import Levenshtein

from .listing import Listing


@dataclass
class DedupResult:
    is_duplicate: bool
    existing_listing_id: int | None = None
    rule_fired: str | None = None
    previous_price: int | None = None
    price_changed_pct: float | None = None
    is_significant_price_drop: bool = False        # > 5% drop


_NORM_WS = re.compile(r"\s+")
_NORM_PUNCT = re.compile(r"[^\w\s]")
_STREET_SUFFIXES = {
    "street": "st", "avenue": "ave", "boulevard": "blvd", "road": "rd",
    "drive": "dr", "lane": "ln", "court": "ct", "place": "pl",
    "highway": "hwy", "parkway": "pkwy", "terrace": "ter",
    "north": "n", "south": "s", "east": "e", "west": "w",
    "northeast": "ne", "northwest": "nw", "southeast": "se", "southwest": "sw",
}


def normalize_address(s: str | None) -> str:
    if not s:
        return ""
    t = s.lower()
    t = _NORM_PUNCT.sub(" ", t)
    t = _NORM_WS.sub(" ", t).strip()
    tokens = [_STREET_SUFFIXES.get(tok, tok) for tok in t.split()]
    return " ".join(tokens)


def _within_pct(a: int, b: int, pct: float) -> bool:
    if a == 0 and b == 0:
        return True
    base = max(abs(a), abs(b))
    return abs(a - b) / base <= pct


def find_duplicate(conn: sqlite3.Connection, candidate: Listing) -> DedupResult:
    """Search the listings table for a duplicate of `candidate`."""

    # Rule 1: exact source identity
    if candidate.source_listing_id:
        cur = conn.execute(
            "SELECT id, price FROM listings WHERE source = ? AND source_listing_id = ?",
            (candidate.source, candidate.source_listing_id),
        )
        row = cur.fetchone()
        if row:
            prev_price = int(row["price"])
            pct = (candidate.price - prev_price) / prev_price if prev_price else 0.0
            return DedupResult(
                is_duplicate=True,
                existing_listing_id=int(row["id"]),
                rule_fired="exact_source_id",
                previous_price=prev_price,
                price_changed_pct=pct,
                is_significant_price_drop=pct <= -0.05,
            )

    # Rule 2 + 3: address-based fuzzy
    norm_addr = normalize_address(candidate.address)
    if not norm_addr:
        return DedupResult(is_duplicate=False)

    cur = conn.execute(
        "SELECT id, address, price, tenant FROM listings WHERE channel = ?",
        (candidate.channel,),
    )
    rows: list[Any] = cur.fetchall()
    for row in rows:
        existing_norm = normalize_address(row["address"])
        if not existing_norm:
            continue
        addr_dist = Levenshtein.distance(norm_addr, existing_norm)
        existing_price = int(row["price"])
        prev_price = existing_price

        # Rule 2
        if addr_dist <= 5 and _within_pct(candidate.price, existing_price, 0.02):
            pct = (candidate.price - prev_price) / prev_price if prev_price else 0.0
            return DedupResult(
                is_duplicate=True,
                existing_listing_id=int(row["id"]),
                rule_fired="address_fuzzy_lev5_price2pct",
                previous_price=prev_price,
                price_changed_pct=pct,
                is_significant_price_drop=pct <= -0.05,
            )

        # Rule 3
        existing_tenant = (row["tenant"] or "").strip().lower()
        cand_tenant = (candidate.tenant or "").strip().lower()
        if (cand_tenant and existing_tenant
                and cand_tenant == existing_tenant
                and addr_dist <= 10
                and _within_pct(candidate.price, existing_price, 0.05)):
            pct = (candidate.price - prev_price) / prev_price if prev_price else 0.0
            return DedupResult(
                is_duplicate=True,
                existing_listing_id=int(row["id"]),
                rule_fired="tenant_address_lev10_price5pct",
                previous_price=prev_price,
                price_changed_pct=pct,
                is_significant_price_drop=pct <= -0.05,
            )

    return DedupResult(is_duplicate=False)
