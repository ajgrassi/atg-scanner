"""Mewbourne Oil Co — direct WI offerings.

Subclasses GenericBrokerEmailParser so it inherits the standard LABEL: value body parser.
Override _default_channel() to route to oil_gas_wi.
"""

from __future__ import annotations

from .generic_broker import GenericBrokerEmailParser


class MewbourneParser(GenericBrokerEmailParser):
    source_id = "mewbourne"

    def _default_channel(self) -> str:
        return "oil_gas_wi"
