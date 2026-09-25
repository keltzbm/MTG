"""`riffle ingest prices` and the price step of sync: report problems, never stop the run."""

from datetime import date
from pathlib import Path

from typer.testing import CliRunner

from riffle import net
from riffle.cli import app
from riffle.ingest import scryfall, tcgcsv


def test_ingest_prices_reports_both_sources(monkeypatch):
    monkeypatch.setattr(scryfall, "snapshot_prices", lambda: (Path("/d/2026-09-24.jsonl.gz"), True))
    snap = tcgcsv.Snapshot(day=date(2026, 9, 24), fetched=["fab", "op"], skipped=["mtg"])
    snap.groups, snap.requests = {"fab": 105, "op": 87}, 194
    monkeypatch.setattr(tcgcsv, "snapshot", lambda delay, progress: snap)
    result = CliRunner().invoke(app, ["ingest", "prices"])
    assert result.exit_code == 0, result.output
    assert "scryfall prices: kept 2026-09-24\n" in result.output
    line = "tcgcsv prices: 2026-09-24 · fab 105 groups · op 87 groups · already have mtg · 194 requests"
    assert line in result.output


def test_ingest_prices_survives_both_sources_failing(monkeypatch):
    def no_bulk():
        raise FileNotFoundError("no Scryfall bulk file yet")

    def down(delay, progress):
        raise net.FetchError("no answer after 3 tries")

    monkeypatch.setattr(scryfall, "snapshot_prices", no_bulk)
    monkeypatch.setattr(tcgcsv, "snapshot", down)
    result = CliRunner().invoke(app, ["ingest", "prices"])
    assert result.exit_code == 0, result.output
    assert "scryfall prices: no bulk file yet — run: riffle ingest scryfall" in result.output
    assert "tcgcsv prices: no answer after 3 tries" in result.output


def test_a_game_that_failed_is_named(monkeypatch):
    monkeypatch.setattr(scryfall, "snapshot_prices", lambda: (Path("/d/2026-09-24.jsonl.gz"), False))
    snap = tcgcsv.Snapshot(day=date(2026, 9, 24), fetched=["mtg"], failed=[("fab", "HTTP 503")])
    snap.groups = {"mtg": 456}
    monkeypatch.setattr(tcgcsv, "snapshot", lambda delay, progress: snap)
    result = CliRunner().invoke(app, ["ingest", "prices"])
    assert "scryfall prices: already have 2026-09-24\n" in result.output
    assert "! tcgcsv prices: fab: HTTP 503" in result.output
