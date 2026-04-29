"""Oil & Gas Clearinghouse.

Subclasses GenericBrokerEmailParser so it inherits the standard LABEL: value body parser.
Override _default_channel() to route to oil_gas_wi.
"""

from __future__ import annotations

from .generic_broker import GenericBrokerEmailParser


class OgClearinghouseParser(GenericBrokerEmailParser):
    source_id = "og_clearinghouse"

    def _default_channel(self) -> str:
        return "oil_gas_wi"
