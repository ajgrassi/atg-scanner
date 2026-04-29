"""Entry point for the daily routine.

CLI surface (Phase 1):
    atg-scanner --help
    atg-scanner db init
    atg-scanner db status
    atg-scanner run-once [--dry-run] [--since 24h]

run-once is currently a stub: it migrates the DB, logs the scoping query
that the routine will use, and writes a heartbeat run-log entry. The actual
parser/scorer/digest path lights up in Phases 2–4.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click

from . import db, pipeline
from .config import (
    db_path,
    gmail_from_query,
    get_settings,
    run_log_path,
)
from .gmail_client import default_client
from .utils import configure_logging, get_logger, utc_now


log = get_logger("atg-scanner")


# -------------------------------------------------------- CLI


@click.group(help="ATG Deal Scanner — daily routine.")
@click.version_option("0.1.0", prog_name="atg-scanner")
def cli() -> None:
    configure_logging()


@cli.group("db")
def db_group() -> None:
    """Database commands."""


@db_group.command("init")
def db_init() -> None:
    db.migrate()
    click.echo(f"DB ready at {db_path()}")


@db_group.command("status")
def db_status() -> None:
    db.migrate()
    counts = db.row_counts()
    click.echo(f"DB: {db_path()}")
    for table, n in counts.items():
        click.echo(f"  {table:<16} {n:>7,}")


@cli.command("run-once", help="Run the daily routine end-to-end once.")
@click.option("--dry-run", is_flag=True, help="Skip the Gmail draft creation step.")
@click.option("--since", default="24h", show_default=True,
              help="Window for 'after:' Gmail filter (e.g. 24h, 7d).")
@click.option("--max-messages", type=int, default=200, show_default=True,
              help="Hard cap on Gmail messages processed per run.")
def run_once(dry_run: bool, since: str, max_messages: int) -> None:
    db.migrate()
    s = get_settings()
    cutoff = utc_now() - _parse_window(since)

    log.info("run.start", digest_recipient=s.digest_recipient,
             cutoff=cutoff.isoformat(), dry_run=dry_run)

    summary = pipeline.run(
        client=default_client(),
        since=cutoff,
        dry_run=dry_run,
        max_messages=max_messages,
    )
    _append_run_log(summary)
    log.info(
        "run.done",
        **{k: v for k, v in summary.items()
           if k not in ("gmail_query", "parser_failures")},
    )


@cli.command("verify-setup", help="Smoke-check that all parts of the pipeline import + initialize.")
def verify_setup() -> None:
    db.migrate()
    from .config import ALL_CHANNELS, gmail_from_query
    from .scorers import get_scorer
    import importlib
    from .config import SOURCES

    click.echo(f"DB: {db_path()} — OK")
    click.echo(f"Gmail query (length {len(gmail_from_query())}): "
               f"{gmail_from_query()[:90]}...")
    click.echo(f"Channels: {len(ALL_CHANNELS)}")
    for ch in ALL_CHANNELS:
        scorer = get_scorer(ch)
        click.echo(f"  scorer.{ch}: {scorer.__class__.__name__}")
    parser_names = {entry[1] for entry in SOURCES.values()} | {"pdf_om", "generic_broker"}
    click.echo(f"Parsers: {len(parser_names)}")
    failed: list[str] = []
    for name in sorted(parser_names):
        try:
            mod = importlib.import_module(f"app.parsers.{name}")
            cls = next(
                (v for v in vars(mod).values()
                 if isinstance(v, type) and v.__name__.endswith("Parser")
                 and v.__module__ == mod.__name__), None,
            )
            assert cls is not None
            cls()
            click.echo(f"  parser.{name}: {cls.__name__}")
        except Exception as e:                              # noqa: BLE001
            failed.append(f"{name}: {e}")
            click.echo(f"  parser.{name}: FAIL — {e}")
    if failed:
        raise click.ClickException(f"{len(failed)} parser(s) failed to load")
    click.echo("verify-setup OK")


# -------------------------------------------------------- helpers


_WINDOW = re.compile(r"^(\d+)\s*(h|d)$", re.I)


def _parse_window(s: str) -> timedelta:
    m = _WINDOW.match(s.strip())
    if not m:
        raise click.BadParameter(f"--since must look like '24h' or '7d', got: {s!r}")
    n = int(m.group(1))
    unit = m.group(2).lower()
    return timedelta(hours=n) if unit == "h" else timedelta(days=n)


def _append_run_log(entry: dict) -> None:
    p = run_log_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    if p.exists():
        try:
            rows = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(rows, list):
                rows = []
        except json.JSONDecodeError:
            rows = []
    rows.append(entry)
    # Keep the last 365 entries.
    rows = rows[-365:]
    p.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    cli()
