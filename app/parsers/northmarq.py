"""NorthMarq — car wash NNN.

Subclasses GenericBrokerEmailParser so it inherits the standard LABEL: value body parser.
Override _default_channel() to route to car_wash_nnn.
"""

from __future__ import annotations

from .generic_broker import GenericBrokerEmailParser


class NorthmarqParser(GenericBrokerEmailParser):
    source_id = "northmarq"

    def _default_channel(self) -> str:
        return "car_wash_nnn"
