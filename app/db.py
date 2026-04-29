"""SQLite schema + simple operations.

Two tables:
  listings       — one row per unique listing
  listing_events — append-only log of price changes, status changes, scoring snapshots

Schema is intentionally additive — migrations happen by ADDING columns. Use
`migrate()` after pulling new code; it's idempotent and safe to run repeatedly.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterator

from .config import db_path
from .utils import get_logger

log = get_logger(__name__)


SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identity
    source                   TEXT NOT NULL,
    source_listing_id        TEXT,
    channel                  TEXT NOT NULL,
    listing_url              TEXT,
    email_id                 TEXT NOT NULL,

    -- Property basics
    title                    TEXT NOT NULL,
    address                  TEXT NOT NULL,
    city                     TEXT,
    state                    TEXT,
    zip                      TEXT,

    -- Financials
    price                    INTEGER NOT NULL,
    cap_rate                 REAL,
    noi                      INTEGER,
    sf                       INTEGER,
    lot_acres                REAL,

    -- Lease (NNN deals)
    tenant                   TEXT,
    tenant_credit            TEXT,
    lease_type               TEXT,
    lease_start              TEXT,
    lease_expiration         TEXT,
    term_remaining_years     REAL,
    escalator_pct            REAL,
    roof_structure           TEXT,

    -- Tax
    bonus_dep_eligible       INTEGER,            -- 0 / 1
    estimated_cost_seg_pct   REAL,

    -- Scoring snapshot (most recent)
    score                    REAL,
    verdict                  TEXT,                -- PURSUE / PURSUE_CONDITIONS / WATCH / PASS / STRUCTURAL_FAIL
    score_components_json    TEXT,
    structural_failures_json TEXT,

    -- Metadata
    extraction_confidence    REAL,
    needs_review             INTEGER NOT NULL DEFAULT 0,
    raw_data_json            TEXT,
    first_seen               TEXT NOT NULL,
    last_seen                TEXT NOT NULL,

    UNIQUE(source, source_listing_id)
);

CREATE INDEX IF NOT EXISTS idx_listings_channel        ON listings(channel);
CREATE INDEX IF NOT EXISTS idx_listings_first_seen     ON listings(first_seen);
CREATE INDEX IF NOT EXISTS idx_listings_address        ON listings(address);
CREATE INDEX IF NOT EXISTS idx_listings_verdict_score  ON listings(verdict, score);


CREATE TABLE IF NOT EXISTS listing_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id    INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    event_type    TEXT NOT NULL,                 -- price_change / status_change / score_change / parser_warning
    occurred_at   TEXT NOT NULL,
    details_json  TEXT
);

CREATE INDEX IF NOT EXISTS idx_listing_events_listing  ON listing_events(listing_id, occurred_at);
"""


def _connect() -> sqlite3.Connection:
    p = db_path()
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate() -> None:
    """Idempotent — safe to call on every routine fire."""
    with transaction() as conn:
        conn.executescript(SCHEMA)
    log.info("db.migrate.ok", path=str(db_path()))


def row_counts() -> dict[str, int]:
    with transaction() as conn:
        out: dict[str, int] = {}
        for table in ("listings", "listing_events"):
            cur = conn.execute(f"SELECT COUNT(*) AS n FROM {table}")
            out[table] = int(cur.fetchone()["n"])
        return out


# -------------------------------------------------------- helpers


def _json(v: Any) -> str | None:
    if v is None:
        return None
    return json.dumps(v, default=_json_default, separators=(",", ":"))


def _json_default(v: Any) -> Any:
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if hasattr(v, "__dict__"):
        return v.__dict__
    return str(v)
