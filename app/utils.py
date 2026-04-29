"""Small helpers used across modules."""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone

import structlog

from .config import get_settings


def configure_logging() -> None:
    """structlog → stdlib bridge; key=value lines on stderr."""
    s = get_settings()
    level = getattr(logging, s.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(message)s",
        stream=sys.stderr,
    )
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
