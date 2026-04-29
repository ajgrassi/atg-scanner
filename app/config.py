"""Configuration: env loading, channel definitions, source→parser mapping.

Source of truth for what counts as a broker email and how it routes. Edit
SOURCES + SAVED_SEARCH_TO_CHANNEL when Andrew adds a new sender.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------------------------------------------------------------- channels

Channel = Literal[
    "car_wash_nnn",
    "msa_commercial",
    "self_storage",
    "oil_gas_wi",
    "solar",
    "ios",
]

ALL_CHANNELS: tuple[Channel, ...] = (
    "car_wash_nnn",
    "msa_commercial",
    "self_storage",
    "oil_gas_wi",
    "solar",
    "ios",
)


# ---------------------------------------------------------------- sources

#: Sender pattern → (channel(s), parser module name in app.parsers).
#: A pattern is matched against the From: header (lowercased). Patterns
#: starting with "*@" match any local part of that domain. Patterns without
#: "*" must match the full local-part@domain. The LongerString-First rule
#: applies (see resolve_source()).
SOURCES: dict[str, tuple[tuple[Channel, ...], str]] = {
    "noreply@crexi.com":               (("__route_by_subject__",), "crexi"),         # type: ignore[dict-item]
    "alerts@loopnet.com":              (("__route_by_subject__",), "loopnet"),        # type: ignore[dict-item]
    "*@sandsig.com":                   (("car_wash_nnn", "ios"), "sands_ig"),
    "*@signnn.com":                    (("car_wash_nnn", "ios"), "sands_ig"),
    "eric.carlton@colliers.com":       (("car_wash_nnn",), "snyder_carlton"),
    "jereme.snyder@colliers.com":      (("car_wash_nnn",), "snyder_carlton"),
    "*@tradenetlease.com":             (("car_wash_nnn",), "b_and_e"),
    "*@hanleyinvestment.com":          (("car_wash_nnn",), "hanley"),
    "*@matthews.com":                  (("car_wash_nnn", "msa_commercial"), "matthews"),
    "*@northmarq.com":                 (("car_wash_nnn",), "northmarq"),
    "*@argus-selfstorage.com":         (("self_storage",), "argus_storage"),
    "*@thestoragegroup.com":           (("self_storage",), "storage_group"),
    "*@skyviewadvisors.com":           (("self_storage",), "skyview"),
    "travis@rvstoragebroker.com":      (("self_storage",), "rv_storage_broker"),
    "*@haydenoutdoors.com":            (("self_storage",), "hayden_outdoors"),
    "*@mewbourne.com":                 (("oil_gas_wi",), "mewbourne"),
    "teresa@aec-kc.com":               (("oil_gas_wi",), "aef"),
    "*@aefdyer.com":                   (("oil_gas_wi",), "aef"),
    "*@energynet.com":                 (("oil_gas_wi",), "energynet"),
    "*@ogclearinghouse.com":           (("oil_gas_wi",), "og_clearinghouse"),
    "*@solsystems.com":                (("solar",), "sol_systems"),
    "*@energea.com":                   (("solar",), "energea"),
    "*@leveltenenergy.com":            (("solar",), "levelten"),
    "*@zenithios.com":                 (("ios",), "zenith_ios"),
    "*@alterraproperty.com":           (("ios",), "alterra"),
}


#: Crexi/LoopNet subject-line saved-search-name → channel.
#: Match is case-insensitive substring.
SAVED_SEARCH_TO_CHANNEL: dict[str, Channel] = {
    "self storage national":      "self_storage",
    "car wash fee simple":        "car_wash_nnn",
    "springfield commercial":     "msa_commercial",
    "industrial outdoor storage": "ios",
}


def gmail_from_query() -> str:
    """Build a Gmail `from:(...)` clause from SOURCES.

    Used as the broker-email scoping query in the daily routine.
    """
    seen: set[str] = set()
    parts: list[str] = []
    for pattern in SOURCES:
        if pattern.startswith("*@"):
            domain = pattern[2:]
            parts.append(domain)
            seen.add(domain)
        else:
            parts.append(pattern)
            seen.add(pattern)
    # Stable ordering for golden-test stability.
    parts = sorted(set(parts))
    return "from:(" + " OR ".join(parts) + ")"


def resolve_source(from_header: str) -> tuple[tuple[Channel | str, ...], str] | None:
    """Map a raw From: header to (channels, parser-name) per SOURCES.

    Patterns are tried longest-first so an explicit address (e.g.
    `eric.carlton@colliers.com`) wins over a wildcard domain.
    """
    target = from_header.lower()
    # Strip name + angle brackets if present: "Lee McLean <lee@svn.com>" → "lee@svn.com"
    if "<" in target and ">" in target:
        target = target.rsplit("<", 1)[1].rstrip(">").strip()

    candidates = sorted(SOURCES.keys(), key=len, reverse=True)
    for pattern in candidates:
        if pattern.startswith("*@"):
            if target.endswith(pattern[1:]):     # endswith("@domain.com")
                return SOURCES[pattern]
        elif target == pattern:
            return SOURCES[pattern]
    return None


# ---------------------------------------------------------------- env

def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return here.parents[1]


load_dotenv(_repo_root() / ".env", override=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=True)

    digest_recipient:    str = Field(default="agrassi@ybpsrv.com", alias="DIGEST_RECIPIENT")
    digest_sender_name:  str = Field(default="ATG Deal Scanner",   alias="DIGEST_SENDER_NAME")
    timezone:            str = Field(default="America/Chicago",    alias="TIMEZONE")
    draft_magic_prefix:  str = Field(default="[ATG-DIGEST-AUTOSEND]", alias="DRAFT_MAGIC_PREFIX")
    failure_alert_email: str = Field(default="agrassi@ybpsrv.com", alias="FAILURE_ALERT_EMAIL")

    log_level:           str = Field(default="INFO", alias="ATG_LOG_LEVEL")
    data_dir_override:   str = Field(default="",     alias="ATG_DATA_DIR")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def repo_root() -> Path:
    return _repo_root()


def data_dir() -> Path:
    s = get_settings()
    p = Path(s.data_dir_override).expanduser() if s.data_dir_override else _repo_root() / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


def attachments_dir() -> Path:
    p = data_dir() / "attachments"
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    return data_dir() / "deals.db"


def run_log_path() -> Path:
    return data_dir() / "run_log.json"
