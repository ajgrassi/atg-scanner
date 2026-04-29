# ATG Deal Scanner

Daily Claude Code Routine that reads broker email alerts, scores listings against ATG Investments LLC's investment thesis across six asset channels, and drafts a digest email that's auto-sent by a companion Google Apps Script.

See [CLAUDE.md](CLAUDE.md) for the execution spec.

## How it works

```
6:30 AM CT  Claude Routine fires
            └─ Reads broker emails (Gmail connector)
            └─ Parses listings (text body + PDF attachments via pdfplumber)
            └─ Scores against per-channel rubrics
            └─ Writes to data/deals.db
            └─ Creates Gmail draft with subject prefix [ATG-DIGEST-AUTOSEND]

6:35 AM CT  Apps Script fires
            └─ Finds drafts with the magic prefix
            └─ Strips the prefix, sends them
            └─ Original drafts deleted
```

The two-step transport works around the built-in Claude Gmail connector's read+draft-only constraint.

## Channels

| Channel | Price band | What it looks for |
|---|---|---|
| `car_wash_nnn` | $1.5M–$8M | Fee-simple absolute NNN car washes; structural gates on lease type, bonus dep, roof |
| `msa_commercial` | $400k–$1.5M | Springfield MO MSA value-add (Greene/Christian/Webster/Taney counties) |
| `self_storage` | $1.5M–$5M | Self-storage + RV/boat; excludes CA, NY |
| `oil_gas_wi` | $250k–$1.5M | Direct working interests, not funds, not royalty-only |
| `solar` | (varies) | Operational solar farms with ≥15yr PPA remaining |
| `ios` | $2M–$5M | Industrial outdoor storage; ≥2 usable acres |

Per-channel filters, structural gates, and scoring rubrics live in [CLAUDE.md](CLAUDE.md#scoring).

## Setup

```bash
# 1. Install Python 3.11+
# 2. Install uv (fast package manager)
irm https://astral.sh/uv/install.ps1 | iex   # Windows
# curl -LsSf https://astral.sh/uv/install.sh | sh   # Mac/Linux

# 3. Sync dependencies
cd atg-scanner
uv sync

# 4. Configure
cp .env.example .env
# edit .env

# 5. Install the Apps Script (Phase 1.5)
# Open https://script.google.com → New Project
# Paste contents of apps_script/atg_digest_autosender.gs
# Run setupTrigger() once, grant permissions
# Run createTestDraft(), then sendAtgDrafts() to verify

# 6. Smoke test
uv run pytest
uv run atg-scanner --help
uv run atg-scanner run-once --dry-run
```

## CLI

```
atg-scanner run-once               # full daily routine (Gmail search → parse → score → draft)
atg-scanner run-once --dry-run     # parse + score, but skip the Gmail draft step
atg-scanner run-once --since 48h   # override the "since last run" window
atg-scanner run-once --max-messages 50   # cap how many emails to read in one pass
atg-scanner db init                # create SQLite tables
atg-scanner db status              # row counts
atg-scanner verify-setup           # sanity-check imports for every scorer + parser
```

## Project layout

See [CLAUDE.md § Project structure](CLAUDE.md#project-structure).

## Daily routine setup (Phase 5)

Two ways to schedule the daily run:

### Option A — Claude Code Routine (preferred)

The CLAUDE.md spec is the routine's runbook. Configure a routine that:
- Schedule: daily 06:30 America/Chicago
- Working directory: `C:\Users\andyg\Code\atg-scanner`
- Reads CLAUDE.md, then drives the pipeline using the built-in Gmail connector +
  the `atg-scanner` CLI.
- The Apps Script trigger handles delivery at 06:35 CT.

Apps Script trigger is independent — once installed via `setupTrigger()` it runs
on its own daily cadence regardless of whether the routine fires.

### Option B — Local Windows scheduler

Bypasses Claude entirely. The `app/gmail_client.NoOpGmailClient` won't actually
read Gmail, so this path requires you to swap in a real `GmailClient` adapter
(IMAP-based or googleapi-based). Until that adapter ships, Option A is the only
production path.

```powershell
# Stub for future use:
schtasks /Create /TN "ATG Deal Scanner" /TR "C:\path\uv.exe run atg-scanner run-once" `
  /SC DAILY /ST 06:30 /F
```

## Failure handling

If the Gmail connector is unreachable on a given run, the CLI logs the error and
exits non-zero. CLAUDE.md § EXECUTION GUIDANCE step 7 says to create a failure
draft so the Apps Script delivers an alert — that path is wired into the
routine's instructions; the CLI itself doesn't bother because the routine
orchestrator (Claude) is the one with Gmail access.

## Status

| Phase | What | Status |
|---|---|---|
| 1   | Project scaffold + CLI + DB                                    | ✅ done |
| 1.5 | Apps Script installed + tested                                 | ✅ done (per Andrew, 2026-04-27) |
| 2   | PDF OM parser (pdfplumber) + car wash NNN scorer               | ✅ done |
| 3   | Generic broker base + Crexi/LoopNet/Sands IG + run-once wired  | ✅ done |
| 4   | All 23 source parsers (inherited from generic base)            | ✅ done — calibrate against real samples as they arrive |
| 5   | Routine deployment + monitoring                                | ⏳ awaiting Routine registration |

70 unit tests passing. See [CLAUDE.md § STATUS TRACKING](CLAUDE.md#status-tracking).
