"""Smoke-test every parser registered in config.SOURCES.

For each parser:
  - Import it.
  - Instantiate.
  - Feed a generic broker-shaped email body and confirm it returns a Listing.

This catches regressions in shared base behavior (GenericBrokerEmailParser)
and ensures the SOURCES table stays in sync with what's importable.
"""

from __future__ import annotations

import importlib
import pytest

from app.config import SOURCES
from app.gmail_client import EmailMessage
from app.parsers.base import Parser


GENERIC_BODY = """
EXCLUSIVE LISTING — Test Property

500 Industrial Pkwy, Tulsa, OK 74145

Property Highlights
Sale Price: $2,500,000
Building Size: 12,000 SF
Cap Rate: 7.0%
Year Built: 2010

For more information contact your broker.
"""


def _msg(sender: str, subject: str = "Test Listing") -> EmailMessage:
    return EmailMessage(
        id=f"<smoke-{sender}>", thread_id="<t1>",
        sender=sender, subject=subject,
        received_at="2026-04-27T06:00:00Z",
        text_body=GENERIC_BODY, attachments=[],
    )


@pytest.mark.parametrize("parser_name", sorted({entry[1] for entry in SOURCES.values()}))
def test_parser_handles_generic_body(parser_name: str):
    mod = importlib.import_module(f"app.parsers.{parser_name}")
    cls = next(
        (v for v in vars(mod).values()
         if isinstance(v, type) and issubclass(v, Parser) and v is not Parser
         and v.__module__ == mod.__name__),
        None,
    )
    assert cls is not None, f"app.parsers.{parser_name} has no Parser subclass"
    parser = cls()

    # Pick a sender that this parser handles. We use the first SOURCES key
    # whose value points at this parser.
    sender_pattern = next(
        (k for k, v in SOURCES.items() if v[1] == parser_name),
        f"unknown@{parser_name}.com",
    )
    sender = sender_pattern.replace("*@", "info@")
    result = parser.parse(_msg(sender))

    # Generic body has price+SF+address — every parser should yield a listing.
    assert len(result.listings) == 1, \
        f"{parser_name} returned {len(result.listings)} listings; warnings={result.warnings}"
    L = result.listings[0]
    assert L.source == parser_name
    assert L.price == 2_500_000
    assert L.sf == 12_000
    assert L.cap_rate == 0.07
    assert L.address.startswith("500 Industrial Pkwy")
