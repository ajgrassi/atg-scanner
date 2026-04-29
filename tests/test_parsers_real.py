"""Tests for the real parsers (Crexi, LoopNet, Sands IG) using synthetic
broker email bodies. No network."""

from __future__ import annotations

from app.gmail_client import EmailMessage
from app.parsers.crexi import CrexiParser
from app.parsers.loopnet import LoopnetParser
from app.parsers.sands_ig import SandsIgParser


def _msg(sender: str, subject: str, body: str, **kwargs) -> EmailMessage:
    return EmailMessage(
        id=kwargs.pop("id", "<m1>"),
        thread_id=kwargs.pop("thread_id", "<t1>"),
        sender=sender,
        subject=subject,
        received_at=kwargs.pop("received_at", "2026-04-27T06:00:00Z"),
        text_body=body,
        attachments=kwargs.pop("attachments", []),
    )


# ----------------------------------------------------------- Crexi

CREXI_BODY = """
New Match for Your Saved Search: Springfield Commercial

1100 E Walnut St, Springfield, MO 65806
Property Type: Retail
Property Highlights
Asking Price: $720,000  Building Size: 6,200 SF  Cap Rate: 7.5%
Year Built: 1985

View Listing on Crexi → https://www.crexi.com/properties/abc123/1100-e-walnut-st
"""


def test_crexi_parses_alert_and_routes_msa_commercial():
    msg = _msg("noreply@crexi.com",
               "New Match for Your Saved Search: Springfield Commercial",
               CREXI_BODY)
    result = CrexiParser().parse(msg)
    assert len(result.listings) == 1
    L = result.listings[0]
    assert L.source == "crexi"
    assert L.channel == "msa_commercial"
    assert L.address.startswith("1100 E Walnut St")
    assert L.city == "Springfield"
    assert L.state == "MO"
    assert L.price == 720_000
    assert L.sf == 6_200
    assert L.cap_rate == 0.075
    assert L.listing_url == "https://www.crexi.com/properties/abc123/1100-e-walnut-st"
    assert L.source_listing_id == "1100-e-walnut-st"


def test_crexi_routes_car_wash_via_subject():
    msg = _msg("noreply@crexi.com",
               "New Match for Your Saved Search: Car Wash Fee Simple",
               CREXI_BODY)
    result = CrexiParser().parse(msg)
    assert result.listings[0].channel == "car_wash_nnn"


def test_crexi_routes_self_storage_via_subject():
    msg = _msg("noreply@crexi.com",
               "New Match — Self Storage National",
               CREXI_BODY)
    result = CrexiParser().parse(msg)
    assert result.listings[0].channel == "self_storage"


# ----------------------------------------------------------- LoopNet

LOOPNET_BODY = """
LoopNet alert — Industrial Outdoor Storage saved search

200 Hwy 65 N, Ozark, MO 65721
Property Highlights
Asking Price: $2.4M  Building Size: 8,000 SF  Lot Size: 5.2 acres

https://www.loopnet.com/Listing/200-Hwy-65-Ozark-MO/40123456/
"""


def test_loopnet_parses_alert_with_listing_id():
    msg = _msg("alerts@loopnet.com",
               "LoopNet — Industrial Outdoor Storage match",
               LOOPNET_BODY)
    result = LoopnetParser().parse(msg)
    assert len(result.listings) == 1
    L = result.listings[0]
    assert L.source == "loopnet"
    assert L.channel == "ios"
    assert L.price == 2_400_000
    assert L.sf == 8_000
    assert L.lot_acres == 5.2
    assert L.source_listing_id == "40123456"


# ----------------------------------------------------------- Sands IG

SANDS_BODY = """
EXCLUSIVE LISTING — Mister Car Wash, Bridgeville PA

1234 Main Street, Bridgeville, PA 15017

Property Highlights
Sale Price: $4,250,000  Cap Rate: 6.50%  NOI: $276,250
Building Size: 4,150 SF  Lot Size: 1.42 Acres
Tenant: Mister Car Wash  Lease Type: Absolute NNN  Rent Escalator: 1.5%
Roof Responsibility: Tenant
"""


def test_sands_ig_parses_carwash_blast():
    msg = _msg("info@sandsig.com",
               "EXCLUSIVE LISTING — Mister Car Wash, Bridgeville PA",
               SANDS_BODY)
    result = SandsIgParser().parse(msg)
    assert len(result.listings) == 1
    L = result.listings[0]
    assert L.source == "sands_ig"
    assert L.channel == "car_wash_nnn"
    assert L.price == 4_250_000
    assert L.cap_rate == 0.065
    assert L.tenant == "Mister Car Wash"
    assert L.lease_type == "absolute_nnn"
    assert L.escalator_pct == 0.015
    assert L.roof_structure == "tenant"


def test_sands_ig_routes_ios_via_subject():
    msg = _msg("info@sandsig.com",
               "IOS Yard For Sale — Trucking Terminal",
               SANDS_BODY)
    result = SandsIgParser().parse(msg)
    assert result.listings[0].channel == "ios"
