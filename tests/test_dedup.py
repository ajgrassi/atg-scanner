"""Dedup logic — port + extend from commercial-scout/test_dedup.

Three rules per CLAUDE.md § DEDUP LOGIC:
  1. Exact: source + source_listing_id
  2. Address Lev ≤ 5 + price within 2%
  3. Tenant + address Lev ≤ 10 + price within 5%
"""

from __future__ import annotations

import sqlite3

from app import db
from app.deduper import find_duplicate, normalize_address


def _seed(conn: sqlite3.Connection, **fields) -> int:
    defaults = dict(
        source="test", channel="msa_commercial", title="x",
        address="100 Main St", city="Springfield", state="MO",
        price=600_000, email_id="<x>", first_seen="2026-04-27T00:00:00Z",
        last_seen="2026-04-27T00:00:00Z", needs_review=0,
    )
    defaults.update(fields)
    cols = ",".join(defaults.keys())
    placeholders = ",".join("?" for _ in defaults)
    cur = conn.execute(
        f"INSERT INTO listings ({cols}) VALUES ({placeholders})",
        tuple(defaults.values()),
    )
    return int(cur.lastrowid)


def test_normalize_address_handles_directional_abbreviations():
    assert normalize_address("123 East Walnut Street") == normalize_address("123 E Walnut St")


def test_normalize_address_handles_punctuation():
    assert normalize_address("5540 N. Farmer Branch Rd.") == normalize_address(
        "5540 North Farmer Branch Road")


def test_dedup_rule_1_exact_source_id(make_listing):
    db.migrate()
    with db.transaction() as conn:
        existing_id = _seed(conn, source="crexi", source_listing_id="abc123",
                            address="100 Main St", price=600_000)

        candidate = make_listing(
            source="crexi", source_listing_id="abc123",
            address="999 Different St",       # different — irrelevant under rule 1
            price=595_000,
        )
        result = find_duplicate(conn, candidate)
    assert result.is_duplicate is True
    assert result.existing_listing_id == existing_id
    assert result.rule_fired == "exact_source_id"
    assert result.previous_price == 600_000


def test_dedup_rule_2_address_fuzzy_price_within_2pct(make_listing):
    db.migrate()
    with db.transaction() as conn:
        existing_id = _seed(conn, address="123 East Walnut Street", price=500_000)

        candidate = make_listing(
            source="other", source_listing_id="z",
            address="123 E Walnut St",        # Lev distance ≤ 5 after normalize
            price=505_000,                     # 1% diff
        )
        result = find_duplicate(conn, candidate)
    assert result.is_duplicate
    assert result.rule_fired == "address_fuzzy_lev5_price2pct"


def test_dedup_rule_2_rejects_when_price_outside_2pct(make_listing):
    db.migrate()
    with db.transaction() as conn:
        _seed(conn, address="123 E Walnut St", price=500_000)
        candidate = make_listing(
            address="123 E Walnut St",
            price=550_000,                     # 10% diff
        )
        result = find_duplicate(conn, candidate)
    assert result.is_duplicate is False


def test_dedup_rule_3_tenant_address_lev10_price_within_5pct(make_listing):
    db.migrate()
    with db.transaction() as conn:
        _seed(conn, address="100 Wash St", tenant="Mister Car Wash",
              price=3_500_000, channel="car_wash_nnn")
        candidate = make_listing(
            channel="car_wash_nnn",
            address="100 Wash Street Suite 1",   # Lev distance > 5 but ≤ 10
            tenant="Mister Car Wash",
            price=3_400_000,                      # ~3% diff
        )
        result = find_duplicate(conn, candidate)
    assert result.is_duplicate
    assert result.rule_fired == "tenant_address_lev10_price5pct"


def test_significant_price_drop_flag(make_listing):
    db.migrate()
    with db.transaction() as conn:
        _seed(conn, source="crexi", source_listing_id="abc",
              address="200 Main", price=1_000_000)
        candidate = make_listing(
            source="crexi", source_listing_id="abc",
            price=900_000,                          # -10%
        )
        result = find_duplicate(conn, candidate)
    assert result.is_duplicate
    assert result.is_significant_price_drop
