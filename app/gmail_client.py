"""Gmail wrapper — reads broker email + creates the digest draft.

In production the routine runs INSIDE Claude Code with a connected Gmail
MCP. The actual MCP calls happen at the orchestrator level (see CLAUDE.md
§ EXECUTION GUIDANCE) — Claude reads the inbox and creates the draft. The
Python code's job is to:

  - Build the right Gmail search query (see config.gmail_from_query)
  - Build the draft subject + body when handed listings + price drops
  - Provide a stable place to plug in non-MCP transports (IMAP, googleapi)
    if/when we want to run this outside Claude Code.

This module exposes an interface so test code can pass a fake. The default
implementation raises NotImplementedError because the routine doesn't run
this Python module against live Gmail today — Claude does that orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .utils import get_logger

log = get_logger(__name__)


@dataclass
class EmailMessage:
    """Source-agnostic representation of a Gmail message we want to parse."""

    id: str
    thread_id: str
    sender: str
    subject: str
    received_at: str               # ISO-8601
    text_body: str
    html_body: str | None = None
    attachments: list["Attachment"] | None = None


@dataclass
class Attachment:
    filename: str
    mime_type: str
    size_bytes: int
    local_path: str | None = None  # populated after download


@dataclass
class DraftRequest:
    to: list[str]
    subject: str
    html_body: str
    text_body: str | None = None
    cc: list[str] | None = None
    bcc: list[str] | None = None


class GmailClient(Protocol):
    def search(self, query: str, max_results: int = 100) -> list[EmailMessage]: ...
    def fetch_attachments(self, message_id: str, save_dir: str) -> list[Attachment]: ...
    def create_draft(self, draft: DraftRequest) -> str: ...


class NoOpGmailClient:
    """In-process stub used when the routine is invoked outside Claude Code.

    Logs intent but does no I/O. Useful for `--dry-run` and unit tests.
    """

    def search(self, query: str, max_results: int = 100) -> list[EmailMessage]:
        log.info("gmail.noop.search", query=query, max_results=max_results)
        return []

    def fetch_attachments(self, message_id: str, save_dir: str) -> list[Attachment]:
        log.info("gmail.noop.fetch_attachments", message_id=message_id)
        return []

    def create_draft(self, draft: DraftRequest) -> str:
        log.info(
            "gmail.noop.create_draft",
            to=draft.to,
            subject=draft.subject,
            html_len=len(draft.html_body),
        )
        return "noop-draft-id"


def default_client() -> GmailClient:
    """Resolve the Gmail client used at runtime.

    Today: NoOpGmailClient — Claude (the routine orchestrator) is the
    actual Gmail caller. When we add an MCP-bridging Python adapter, swap
    it in here behind an env flag.
    """
    return NoOpGmailClient()
