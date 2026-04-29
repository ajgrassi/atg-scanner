"""Energea — operating solar farm assets.

Subclasses GenericBrokerEmailParser so it inherits the standard LABEL: value body parser.
Override _default_channel() to route to solar.
"""

from __future__ import annotations

from .generic_broker import GenericBrokerEmailParser


class EnergeaParser(GenericBrokerEmailParser):
    source_id = "energea"

    def _default_channel(self) -> str:
        return "solar"
