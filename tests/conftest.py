"""Test fixtures shared across the suite."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def isolated_data_dir(monkeypatch, tmp_path):
    """Point ATG_DATA_DIR at a fresh temp dir per test so we don't pollute
    the user's real data/ folder."""
    monkeypatch.setenv("ATG_DATA_DIR", str(tmp_path))
    # Clear settings cache so the new env var is picked up.
    from app import config
    config.get_settings.cache_clear()
    yield tmp_path
    config.get_settings.cache_clear()


@pytest.fixture
def make_listing():
    """Build a Listing with sane defaults for the msa_commercial channel."""
    from app.listing import Listing

    def _make(**overrides: Any) -> Listing:
        defaults = dict(
            source="test", channel="msa_commercial", title="Test Listing",
            address="123 Test St", city="Springfield", state="MO", zip="65801",
            price=600_000, sf=5_000, email_id="<test@example>",
            raw_data={
                "use_type": "retail",
                "year_built": 1995,
                "occupancy_pct": 85.0,
                "asking_rate_psf": 18.0,
                "county": "Greene",
                "oz_flag": False,
                "description": "",
                "property_facts": {"BuildingSize": "5,000 SF", "YearBuilt": "1995"},
            },
        )
        defaults.update(overrides)
        # If caller passed individual fields like year_built, fold them in.
        for k in ("year_built", "occupancy_pct", "asking_rate_psf", "county",
                  "oz_flag", "description", "use_type"):
            if k in overrides:
                defaults["raw_data"][k] = overrides.pop(k, defaults["raw_data"].get(k))
        return Listing(**defaults)

    return _make
