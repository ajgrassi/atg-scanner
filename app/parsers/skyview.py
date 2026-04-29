"""Skyview Advisors broker broadcast.

Subclasses GenericBrokerEmailParser so it inherits the standard LABEL: value body parser.
Override _default_channel() to route to self_storage.
"""

from __future__ import annotations

from .generic_broker import GenericBrokerEmailParser


class SkyviewParser(GenericBrokerEmailParser):
    source_id = "skyview"

    def _default_channel(self) -> str:
        return "self_storage"
