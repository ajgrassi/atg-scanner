"""LevelTen Energy — solar marketplace.

Subclasses GenericBrokerEmailParser so it inherits the standard LABEL: value body parser.
Override _default_channel() to route to solar.
"""

from __future__ import annotations

from .generic_broker import GenericBrokerEmailParser


class LeveltenParser(GenericBrokerEmailParser):
    source_id = "levelten"

    def _default_channel(self) -> str:
        return "solar"
