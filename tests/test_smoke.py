"""Phase-1 acceptance: the routine fires, logs a hello-world run, no crashes.

Tests:
  - DB migrate is idempotent.
  - run-once writes a run_log entry.
  - The CLI loads without ImportError.
"""

from __future__ import annotations

import json

from click.testing import CliRunner


def test_db_init_creates_tables():
    from app import db
    db.migrate()
    db.migrate()                                # idempotent
    counts = db.row_counts()
    assert counts == {"listings": 0, "listing_events": 0}


def test_run_once_writes_log_entry(tmp_path, monkeypatch):
    from app.config import run_log_path
    from app.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["run-once", "--dry-run", "--since", "24h"])
    assert result.exit_code == 0, result.output

    log_p = run_log_path()
    assert log_p.exists()
    rows = json.loads(log_p.read_text(encoding="utf-8"))
    assert len(rows) >= 1
    last = rows[-1]
    assert last["phase"] in ("1_scaffold", "3_pipeline")
    assert last["dry_run"] is True
    assert last["draft_created"] is False


def test_cli_help_lists_subcommands():
    from app.main import cli
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    for cmd in ("run-once", "db"):
        assert cmd in result.output


def test_db_subcommands_run():
    from app.main import cli
    runner = CliRunner()
    for args in (["db", "init"], ["db", "status"]):
        result = runner.invoke(cli, args)
        assert result.exit_code == 0, f"{args}: {result.output}"


def test_all_scorers_register():
    """Discovery: every channel maps to a Scorer and instantiates."""
    from app.config import ALL_CHANNELS
    from app.scorers import SCORER_BY_CHANNEL, get_scorer

    for ch in ALL_CHANNELS:
        assert ch in SCORER_BY_CHANNEL
        scorer = get_scorer(ch)
        assert scorer.channel == ch


def test_all_parsers_importable():
    """Every parser stub imports cleanly and exposes a parse() method."""
    import importlib
    from app.config import SOURCES

    parser_names = {entry[1] for entry in SOURCES.values()}
    parser_names.add("pdf_om")
    for name in parser_names:
        mod = importlib.import_module(f"app.parsers.{name}")
        # Find the Parser subclass exported by the module.
        cls = next(
            (v for v in vars(mod).values()
             if isinstance(v, type) and v.__name__.endswith("Parser")
             and v.__module__ == mod.__name__),
            None,
        )
        assert cls is not None, f"app.parsers.{name} has no *Parser class"
        assert hasattr(cls, "parse")


def test_gmail_from_query_well_formed():
    from app.config import gmail_from_query
    q = gmail_from_query()
    assert q.startswith("from:(")
    assert q.endswith(")")
    assert "crexi.com" in q
    assert "loopnet.com" in q
