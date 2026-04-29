"""End-to-end pipeline test using a fake GmailClient.

Stitches: search → parser dispatch → dedup → score → persist → digest draft.
Confirms the pipeline runs cleanly against a real (in-memory) DB and emits
a draft when there are matching listings.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import db, pipeline
from app.gmail_client import (
    Attachment,
    DraftRequest,
    EmailMessage,
    GmailClient,
)


CREXI_MATCH_BODY = """
New Match for Your Saved Search: Springfield Commercial

532 E Walnut St, Springfield, MO 65806
Property Type: Retail
Property Highlights
Asking Price: $385,000  Building Size: 3,848 SF  Cap Rate: 7.0%
Year Built: 1960

View Listing on Crexi → https://www.crexi.com/properties/zzz/532-e-walnut
"""


SANDS_MATCH_BODY = """
EXCLUSIVE LISTING — Mister Car Wash, Bridgeville PA

1234 Main Street, Bridgeville, PA 15017

Property Highlights
Sale Price: $4,250,000  Cap Rate: 6.50%  NOI: $276,250
Building Size: 4,150 SF  Lot Size: 1.42 Acres
Tenant: Mister Car Wash  Lease Type: Absolute NNN  Rent Escalator: 1.5%
Roof Responsibility: Tenant
"""


class FakeGmail(GmailClient):
    def __init__(self, messages: list[EmailMessage]) -> None:
        self._messages = messages
        self.created_drafts: list[DraftRequest] = []

    def search(self, query: str, max_results: int = 100) -> list[EmailMessage]:
        return self._messages

    def fetch_attachments(self, message_id: str, save_dir: str) -> list[Attachment]:
        return []

    def create_draft(self, draft: DraftRequest) -> str:
        self.created_drafts.append(draft)
        return f"draft-{len(self.created_drafts)}"


def _msg(id: str, sender: str, subject: str, body: str) -> EmailMessage:
    return EmailMessage(
        id=id, thread_id=f"th-{id}", sender=sender, subject=subject,
        received_at="2026-04-27T06:00:00Z", text_body=body, attachments=[],
    )


def test_pipeline_e2e_creates_draft():
    db.migrate()
    client = FakeGmail([
        _msg("<a>", "noreply@crexi.com",
             "New Match for Your Saved Search: Springfield Commercial",
             CREXI_MATCH_BODY),
        _msg("<b>", "info@sandsig.com",
             "EXCLUSIVE LISTING — Mister Car Wash, Bridgeville PA",
             SANDS_MATCH_BODY),
    ])

    summary = pipeline.run(
        client=client,
        since=datetime.now(timezone.utc) - timedelta(hours=24),
        dry_run=False,
    )

    assert summary["emails_processed"] == 2
    assert summary["listings_new"] == 2
    assert summary["draft_created"] is True
    assert "crexi" in summary["sources_active"]
    assert "sands_ig" in summary["sources_active"]
    assert len(client.created_drafts) == 1

    draft = client.created_drafts[0]
    assert draft.subject.startswith("[ATG-DIGEST-AUTOSEND]")
    assert draft.to == ["agrassi@ybpsrv.com"]
    assert "532 E Walnut" in draft.html_body or "Mister Car Wash" in draft.html_body


def test_pipeline_dedupes_repeat_listing():
    db.migrate()
    msg_a = _msg("<a>", "noreply@crexi.com",
                 "New Match for Your Saved Search: Springfield Commercial",
                 CREXI_MATCH_BODY)
    client = FakeGmail([msg_a])

    s1 = pipeline.run(
        client=client, since=datetime.now(timezone.utc) - timedelta(hours=24),
        dry_run=True,
    )
    assert s1["listings_new"] == 1

    # Run again with the same message — should update, not insert.
    s2 = pipeline.run(
        client=client, since=datetime.now(timezone.utc) - timedelta(hours=24),
        dry_run=True,
    )
    assert s2["listings_new"] == 0
    assert s2["listings_updated"] == 1


def test_pipeline_dry_run_skips_draft():
    db.migrate()
    client = FakeGmail([
        _msg("<a>", "noreply@crexi.com",
             "New Match for Your Saved Search: Springfield Commercial",
             CREXI_MATCH_BODY),
    ])
    summary = pipeline.run(
        client=client, since=datetime.now(timezone.utc) - timedelta(hours=24),
        dry_run=True,
    )
    assert summary["draft_created"] is False
    assert client.created_drafts == []


def test_pipeline_quiet_day_no_draft():
    db.migrate()
    client = FakeGmail([])
    summary = pipeline.run(
        client=client, since=datetime.now(timezone.utc) - timedelta(hours=24),
        dry_run=False,
    )
    assert summary["emails_processed"] == 0
    assert summary["listings_new"] == 0
    assert summary["draft_created"] is False
    assert client.created_drafts == []
