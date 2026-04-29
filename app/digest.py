"""Build the daily digest draft body + subject.

Produces a `DraftRequest` that Claude (or a future Python Gmail adapter)
hands to the Gmail connector. Empty payloads → `None` so the routine skips
the draft entirely on quiet days.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from .config import ALL_CHANNELS, get_settings
from .gmail_client import DraftRequest
from .listing import Listing


@dataclass
class DigestRow:
    listing: Listing
    score: float
    verdict: str
    components_top3: list[tuple[str, float]] = field(default_factory=list)


@dataclass
class PriceDropRow:
    listing: Listing
    old_price: int
    new_price: int
    pct_change: float
    current_verdict: str


@dataclass
class ScanStats:
    emails_processed: int = 0
    listings_found: int = 0
    listings_new: int = 0
    listings_updated: int = 0
    sources_active: list[str] = field(default_factory=list)
    sources_failed: list[str] = field(default_factory=list)


@dataclass
class Digest:
    generated_at: datetime
    overall_top10: list[DigestRow]
    by_channel: dict[str, list[DigestRow]]
    price_drops: list[PriceDropRow]
    stats: ScanStats

    def is_empty(self) -> bool:
        return not (self.overall_top10 or self.price_drops)


# ----------------------------------------------------------- public API

def build_subject(digest: Digest) -> str:
    """Subject pattern: `[ATG-DIGEST-AUTOSEND] ATG Deal Digest — Mon DD — N new, top score X/100`.

    The Apps Script strips the prefix before sending.
    """
    s = get_settings()
    n = digest.stats.listings_new
    top = max((r.score for r in digest.overall_top10), default=0.0)
    # Format day-of-month with no leading zero, portably across POSIX (`%-d`)
    # and Windows (no equivalent — strip leading zero manually).
    if hasattr(digest.generated_at, "strftime"):
        when = (f"{digest.generated_at:%a %b} "
                f"{digest.generated_at.day}")
    else:
        when = str(digest.generated_at)
    return (f"{s.draft_magic_prefix} ATG Deal Digest — {when} — "
            f"{n} new, top score {top:.0f}/100")


def build_html(digest: Digest) -> str:
    parts: list[str] = []
    parts.append(_html_open(digest))

    if digest.overall_top10:
        parts.append("<h2>Overall top 10</h2>")
        parts.append(_render_table(digest.overall_top10))

    if digest.price_drops:
        parts.append("<h2>Price drops (>5%)</h2>")
        parts.append(_render_price_drops(digest.price_drops))

    for ch in ALL_CHANNELS:
        rows = digest.by_channel.get(ch, [])
        if not rows:
            continue
        parts.append(f"<h2>{_channel_label(ch)} — top {min(5, len(rows))}</h2>")
        parts.append(_render_table(rows[:5]))

    parts.append(_render_stats(digest.stats))
    parts.append("</div></body></html>")
    return "".join(parts)


def build_draft(digest: Digest) -> DraftRequest | None:
    """Return a DraftRequest ready to hand to the Gmail connector, or None
    on quiet days (no new listings + no price drops)."""
    if digest.is_empty():
        return None
    s = get_settings()
    return DraftRequest(
        to=[s.digest_recipient],
        subject=build_subject(digest),
        html_body=build_html(digest),
    )


# ----------------------------------------------------------- HTML helpers

def _html_open(digest: Digest) -> str:
    return (
        "<!doctype html><html><body style=\"font-family:-apple-system,Segoe UI,sans-serif;"
        "background:#f8fafc;margin:0;padding:24px;\">"
        "<div style=\"max-width:680px;margin:0 auto;background:#fff;border:1px solid #e2e8f0;"
        "border-radius:8px;padding:24px;\">"
        f"<h1 style=\"margin:0;font-size:20px;\">ATG Deal Digest</h1>"
        f"<div style=\"color:#64748b;font-size:12px;margin-bottom:16px;\">"
        f"{digest.generated_at:%A, %B %d %Y %H:%M %Z}</div>"
    )


_CHANNEL_LABELS = {
    "car_wash_nnn":   "Car Wash NNN",
    "msa_commercial": "MSA Commercial",
    "self_storage":   "Self-Storage + RV/Boat",
    "oil_gas_wi":     "Oil & Gas Working Interests",
    "solar":          "Solar Farms",
    "ios":            "Industrial Outdoor Storage",
}


def _channel_label(ch: str) -> str:
    return _CHANNEL_LABELS.get(ch, ch.replace("_", " ").title())


def _render_table(rows: Iterable[DigestRow]) -> str:
    out: list[str] = []
    for r in rows:
        L = r.listing
        cap = f"{L.cap_rate:.2%}" if L.cap_rate is not None else "—"
        url = f' href="{L.listing_url}" target="_blank" rel="noopener"' if L.listing_url else ""
        components = ", ".join(f"{k}: {v:.1f}" for k, v in r.components_top3) or "—"
        out.append(
            "<div style=\"border-top:1px solid #e2e8f0;padding:12px 0;\">"
            f"<div style=\"font-weight:600;\"><a{url} style=\"color:#0f172a;text-decoration:none;\">"
            f"{L.title or L.address}</a></div>"
            f"<div style=\"color:#475569;font-size:13px;margin:2px 0;\">"
            f"{L.address}{', ' + L.city if L.city else ''} · ${L.price:,} · {cap}</div>"
            f"<div style=\"color:#475569;font-size:13px;margin:2px 0;\">"
            f"<strong>{r.verdict}</strong> · score {r.score:.0f}/100 · {components}</div>"
            "</div>"
        )
    return "".join(out)


def _render_price_drops(rows: Iterable[PriceDropRow]) -> str:
    out: list[str] = []
    for r in rows:
        L = r.listing
        url = f' href="{L.listing_url}" target="_blank" rel="noopener"' if L.listing_url else ""
        out.append(
            "<div style=\"border-top:1px solid #e2e8f0;padding:12px 0;font-size:13px;color:#475569;\">"
            f"<div style=\"font-weight:600;color:#0f172a;\"><a{url} style=\"color:#0f172a;text-decoration:none;\">"
            f"{L.title or L.address}</a></div>"
            f"${r.old_price:,} → ${r.new_price:,} ({r.pct_change:+.1%}) · {r.current_verdict}"
            "</div>"
        )
    return "".join(out)


def _render_stats(stats: ScanStats) -> str:
    return (
        "<hr style=\"border:0;border-top:1px solid #e2e8f0;margin:24px 0;\" />"
        f"<div style=\"color:#64748b;font-size:12px;\">"
        f"Scan: {stats.emails_processed} emails processed · "
        f"{stats.listings_found} listings found · "
        f"{stats.listings_new} new · "
        f"{stats.listings_updated} updated. "
        f"Active sources: {', '.join(stats.sources_active) or '—'}. "
        f"Failed: {', '.join(stats.sources_failed) or '—'}."
        "</div>"
    )
