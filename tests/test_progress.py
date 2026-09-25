"""The progress displays: timestamped lines off a terminal, Rich's live display on one."""

import io
import itertools
import sys
from datetime import datetime

import pytest
from rich.console import Console
from rich.progress import Progress

from riffle import progress


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (0.04, "0.0s"),
        (8.25, "8.2s"),
        (59.96, "1m 00s"),
        (114, "1m 54s"),
        (3599.6, "1h 00m"),
        (7500, "2h 05m"),
    ],
)
def test_elapsed(seconds, text):
    assert progress.elapsed(seconds) == text


def test_silent_tracker_accepts_everything():
    step = progress.SILENT.step("anything", total=3, unit="groups")
    step.update(1)
    step.ok("done")
    step.fail("no")
    step.drop()


def test_log_lines_are_timestamped_and_failures_go_to_stderr():
    out, err = io.StringIO(), io.StringIO()
    ticks = itertools.count(0.0, 8.25)
    log = progress.LogTracker(out, err, clock=lambda: next(ticks), now=lambda: datetime(2026, 9, 25, 7, 0, 3))
    log.header("riffle sync")
    prices = log.step("Scryfall prices")
    prices.update(5, 10)
    prices.ok("kept 2026-09-24")
    log.step("card catalog").ok()
    log.step("tcgcsv fab").fail("HTTP 503")
    log.step("quiet").drop()
    assert out.getvalue() == (
        "2026-09-25 07:00:03  riffle sync\n"
        "07:00:03  Scryfall prices: kept 2026-09-24 (8.2s)\n"
        "07:00:03  card catalog (8.2s)\n"
    )
    assert err.getvalue() == "07:00:03  ! tcgcsv fab: HTTP 503\n"


def _task(total, done, unit):
    bar = Progress()
    bar.update(bar.add_task("x", total=total, unit=unit), completed=done)
    return bar.tasks[0]


@pytest.mark.parametrize(
    ("total", "done", "unit", "text"),
    [
        (105, 43, "groups", "43/105 groups"),
        (None, 0, "", ""),
        (10_000_000, 2_500_000, "bytes", "2.5/10.0 MB"),
        (None, 2_500_000, "bytes", "2.5 MB"),
    ],
)
def test_amount_shows_counts_or_bytes(total, done, unit, text):
    assert str(progress._amount(_task(total, done, unit))) == text


def test_live_display_turns_finished_steps_into_lines():
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=True, width=100, color_system=None)
    with progress.LiveTracker(console) as live:
        bulk = live.step("Scryfall bulk data", unit="bytes")
        bulk.update(5_000_000, 10_000_000)
        bulk.ok("148.2 MB, Scryfall 2026-09-24")
        live.step("tcgcsv fab", unit="groups").fail("HTTP 503")
        live.step("Scryfall prices").drop()
        assert live.progress.tasks == []  # nothing left running
    text = buf.getvalue()
    assert "✔ Scryfall bulk data" in text and "148.2 MB, Scryfall 2026-09-24" in text
    assert "✘ tcgcsv fab" in text and "HTTP 503" in text


class _Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_open_tracker_is_live_on_a_terminal(monkeypatch):
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setattr(sys, "stdout", _Terminal())
    with progress.open_tracker("riffle sync") as tracker:
        assert isinstance(tracker, progress.LiveTracker)


def test_open_tracker_writes_plain_lines_otherwise(capsys):
    with progress.open_tracker("riffle sync") as tracker:
        assert isinstance(tracker, progress.LogTracker)
        tracker.step("card catalog").ok("118,389 printings")
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].endswith("  riffle sync") and len(lines[0]) == len("2026-09-25 07:00:03  riffle sync")
    assert "  card catalog: 118,389 printings (" in lines[1]
