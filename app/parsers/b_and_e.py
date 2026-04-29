"""B+E / Trade Net Lease — car wash NNN.

Subclasses GenericBrokerEmailParser so it inherits the standard LABEL: value body parser.
Override _default_channel() to route to car_wash_nnn.
"""

from __future__ import annotations

from .generic_broker import GenericBrokerEmailParser


class BAndEParser(GenericBrokerEmailParser):
    source_id = "b_and_e"

    def _default_channel(self) -> str:
        return "car_wash_nnn"
