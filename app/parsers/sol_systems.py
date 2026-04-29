"""Sol Systems — solar PPA marketplace.

Subclasses GenericBrokerEmailParser so it inherits the standard LABEL: value body parser.
Override _default_channel() to route to solar.
"""

from __future__ import annotations

from .generic_broker import GenericBrokerEmailParser


class SolSystemsParser(GenericBrokerEmailParser):
    source_id = "sol_systems"

    def _default_channel(self) -> str:
        return "solar"
