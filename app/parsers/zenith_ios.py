"""Zenith IOS — industrial outdoor storage.

Subclasses GenericBrokerEmailParser so it inherits the standard LABEL: value body parser.
Override _default_channel() to route to ios.
"""

from __future__ import annotations

from .generic_broker import GenericBrokerEmailParser


class ZenithIosParser(GenericBrokerEmailParser):
    source_id = "zenith_ios"

    def _default_channel(self) -> str:
        return "ios"
