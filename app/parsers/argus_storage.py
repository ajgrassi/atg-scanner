"""Argus Self Storage broker broadcast.

Subclasses GenericBrokerEmailParser so it inherits the standard LABEL: value body parser.
Override _default_channel() to route to self_storage.
"""

from __future__ import annotations

from .generic_broker import GenericBrokerEmailParser


class ArgusStorageParser(GenericBrokerEmailParser):
    source_id = "argus_storage"

    def _default_channel(self) -> str:
        return "self_storage"
