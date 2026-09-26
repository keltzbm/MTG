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


@pytest.mark.parametrize(
    ("fraction", "cells"),
    [
        (0, [0, 0, 0, 0]),
        (1 / 32, [1, 0, 0, 0]),  # the leading cell starts at the bottom
        (7 / 32, [7, 0, 0, 0]),
        (8 / 32, [8, 0, 0, 0]),  # and fills before the next one begins
        (9 / 32, [8, 1, 0, 0]),
        (0.999, [8, 8, 8, 7]),  # full only when done
        (1, [8, 8, 8, 8]),
        (1.5, [8, 8, 8, 8]),
        (-0.5, [0, 0, 0, 0]),
    ],
)
def test_a_bar_fills_one_cell_from_the_bottom_up_before_the_next(fraction, cells):
    assert progress.filled(fraction, width=4) == cells


@pytest.mark.parametrize(
    ("step", "cells"),
    [
        (0, [0] * 8),  # about to come in at the left
        (5, [5, 0, 0, 0, 0, 0, 0, 0]),  # its front rises in the first cell
        (20, [4, 8, 4, 0, 0, 0, 0, 0]),  # back cell half empty, front cell half full
        (64, [0, 0, 0, 0, 0, 0, 8, 8]),  # at the right end
        (76, [0, 0, 0, 0, 0, 0, 0, 4]),  # on its way out
        (80, [0] * 8),  # and around again
        (85, [5, 0, 0, 0, 0, 0, 0, 0]),
    ],
)
def test_a_bar_without_a_total_slides_a_block_an_eighth_at_a_time(step, cells):
    assert progress.sliding(step, width=8) == cells


def test_the_sliding_block_keeps_its_size_while_inside_the_bar():
    assert {sum(progress.sliding(step, width=8)) for step in range(16, 65)} == {16}


def test_the_bar_is_green_blocks_over_a_dim_track():
    bar = Progress()
    bar.update(bar.add_task("x", total=4), completed=1)
    text = progress._bar(bar.tasks[0])
    assert text.plain == "█" * 7 + "▁" * 21
    assert {str(s.style) for s in text.spans[:7]} == {"green"}
    assert {str(s.style) for s in text.spans[7:]} == {"dim"}


def test_a_step_without_a_total_or_with_nothing_to_do_still_draws():
    bar = Progress()
    bar.add_task("waiting", total=None)
    bar.add_task("nothing", total=0)
    waiting, nothing = (progress._bar(task).plain for task in bar.tasks)
    assert len(waiting) == progress.BAR_WIDTH and set(waiting) <= set("▁▂▃▄▅▆▇█")
    assert nothing == "█" * progress.BAR_WIDTH


def test_the_live_display_draws_block_bars():
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=True, width=100, color_system=None)
    live = progress.LiveTracker(console)
    live.step("tcgcsv mtg", total=8, unit="groups").update(3)
    console.print(live.progress.make_tasks_table(live.progress.tasks))
    assert "█" * 10 + "▄" + "▁" * 17 in buf.getvalue()  # 3/8 of 28 cells is 10.5


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
