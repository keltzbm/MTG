"""Progress for long-running work, shown while it happens.

Ingest code reports through a Tracker and never draws anything itself: it
opens a step, updates it with a count (or bytes) as work proceeds, and ends it
with ok(note), fail(why), or drop() when there's nothing worth recording.

The CLI picks the display with open_tracker(). On a terminal, Rich draws a line per
running step: a spinner, a bar of block cells (see filled() and sliding()), the
count or bytes and speed, and the time so far. A finished step turns into a
permanent line, a green ✔ (or a red ✘) with its note and how long it took, printed
in order with everything else the command says. Anywhere else, notably the scheduled
job's sync.log, nothing animates: a dated line when the run starts, then a
timestamped line as each step ends."""

import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol, TextIO

if TYPE_CHECKING:
    from rich.console import Console
    from rich.progress import Progress, Task, TaskID
    from rich.text import Text

LABEL_WIDTH = 20
BAR_WIDTH = 28  # cells
REFRESH = 20  # redraws a second: a sliding block moves half a cell per redraw
SLIDE_SPEED = 10  # cells a second, for the block on a bar with no total
_RISE = "▁▂▃▄▅▆▇█"  # a cell filled one to eight eighths, from the bottom up
_TRACK = "▁"  # an empty cell, drawn dim


class Step(Protocol):
    def update(self, done: int, total: int | None = None) -> None: ...
    def ok(self, note: str = "") -> None: ...
    def fail(self, why: str) -> None: ...
    def drop(self) -> None: ...


class Tracker(Protocol):
    def step(self, label: str, total: int | None = None, unit: str = "") -> Step: ...


class _Silent:
    """Reports nowhere; the default for code called outside the CLI. Its own step."""

    def step(self, label: str, total: int | None = None, unit: str = "") -> "_Silent":
        return self

    def update(self, done: int, total: int | None = None) -> None:
        pass

    def ok(self, note: str = "") -> None:
        pass

    def fail(self, why: str) -> None:
        pass

    def drop(self) -> None:
        pass


SILENT: Tracker = _Silent()


class Watched:
    """Passes every step on to another tracker and remembers which ones failed, so a
    command can finish its work and still exit non-zero."""

    def __init__(self, inner: Tracker) -> None:
        self.inner = inner
        self.failed: list[str] = []

    def step(self, label: str, total: int | None = None, unit: str = "") -> "_WatchedStep":
        return _WatchedStep(self, label, self.inner.step(label, total, unit))


class _WatchedStep:
    def __init__(self, watched: Watched, label: str, inner: Step) -> None:
        self._watched, self._label, self._inner = watched, label, inner

    def update(self, done: int, total: int | None = None) -> None:
        self._inner.update(done, total)

    def ok(self, note: str = "") -> None:
        self._inner.ok(note)

    def fail(self, why: str) -> None:
        self._watched.failed.append(self._label)
        self._inner.fail(why)

    def drop(self) -> None:
        self._inner.drop()


def elapsed(seconds: float) -> str:
    """8.2s, 1m 54s, 2h 05m."""
    if seconds < 59.95:  # would round to 60.0s
        return f"{seconds:.1f}s"
    minutes, secs = divmod(round(seconds), 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


# ---- plain lines, for logs and pipes ---------------------------------------------------


class LogTracker:
    """A timestamped line per finished step. Streams are looked up when written,
    so output lands wherever sys.stdout and sys.stderr point at the time."""

    def __init__(
        self,
        out: TextIO | None = None,
        err: TextIO | None = None,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._out, self._err, self.clock, self.now = out, err, clock, now

    def write(self, line: str, error: bool = False) -> None:
        stream = (self._err or sys.stderr) if error else (self._out or sys.stdout)
        print(line, file=stream, flush=True)

    def header(self, title: str) -> None:
        self.write(f"{self.now():%Y-%m-%d %H:%M:%S}  {title}")

    def step(self, label: str, total: int | None = None, unit: str = "") -> "_LogStep":
        return _LogStep(self, label)


class _LogStep:
    def __init__(self, tracker: LogTracker, label: str) -> None:
        self._tracker, self._label, self._start = tracker, label, tracker.clock()

    def update(self, done: int, total: int | None = None) -> None:
        pass

    def ok(self, note: str = "") -> None:
        took = elapsed(self._tracker.clock() - self._start)
        what = f"{self._label}: {note}" if note else self._label
        self._tracker.write(f"{self._tracker.now():%H:%M:%S}  {what} ({took})")

    def fail(self, why: str) -> None:
        self._tracker.write(f"{self._tracker.now():%H:%M:%S}  ! {self._label}: {why}", error=True)

    def drop(self) -> None:
        pass


# ---- the live display, for a terminal --------------------------------------------------


def _amount(task: "Task") -> "Text":
    """The count or bytes column: 43/105 groups, 12.3/148.0 MB  8.1 MB/s."""
    from rich.text import Text

    unit = task.fields.get("unit", "")
    if unit == "bytes":
        text = f"{task.completed / 1e6:,.1f}"
        if task.total:
            text += f"/{task.total / 1e6:,.1f}"
        text += " MB"
        if task.speed:
            text += f"  {task.speed / 1e6:,.1f} MB/s"
    elif task.total is not None:
        text = f"{task.completed:,.0f}/{task.total:,.0f} {unit}".rstrip()
    else:
        text = ""
    return Text(text, style="progress.download")


def filled(fraction: float, width: int = BAR_WIDTH) -> list[int]:
    """Each cell's fill, in eighths, for a bar `fraction` done: whole cells, then the
    leading cell part of the way up, then empty track."""
    return _covered(0, int(min(max(fraction, 0.0), 1.0) * width * 8), width)


def sliding(step: int, width: int = BAR_WIDTH) -> list[int]:
    """Each cell's fill for a bar with no total, `step` eighths of a cell into the
    animation: a block a quarter of the bar long slides in at the left and out at the
    right, then again. Its front cell fills from the bottom up as its back cell empties,
    so it moves an eighth of a cell at a time."""
    size = max(1, width // 4)
    head = step % ((width + size) * 8)
    return _covered(head - size * 8, head, width)


def _covered(tail: int, head: int, width: int) -> list[int]:
    """How much of each cell, in eighths, lies between tail and head (also in eighths)."""
    return [max(0, min(8 * i + 8, head) - max(8 * i, tail)) for i in range(width)]


def _bar(task: "Task") -> "Text":
    """A task's bar: filled to its share of the total, or a block sliding along the track
    when there's no total."""
    from rich.text import Text

    if task.total is None:
        cells = sliding(int(task.get_time() * SLIDE_SPEED * 8))
    else:
        cells = filled(task.completed / task.total if task.total else 1.0)
    bar = Text()
    for eighths in cells:
        if eighths:
            bar.append(_RISE[eighths - 1], "green")
        else:
            bar.append(_TRACK, "dim")
    return bar


class LiveTracker:
    """Running steps redrawn in place; finished steps printed as permanent lines.

    Everything else printed while it's open (typer.echo included) appears above
    the running steps, because Rich redirects stdout and stderr meanwhile.
    """

    def __init__(self, console: "Console") -> None:
        from rich.progress import Progress as RichProgress
        from rich.progress import ProgressColumn, SpinnerColumn, TextColumn, TimeElapsedColumn
        from rich.table import Column

        class Amount(ProgressColumn):
            def render(self, task: "Task") -> "Text":
                return _amount(task)

        class Bar(ProgressColumn):
            def render(self, task: "Task") -> "Text":
                return _bar(task)

        self.console = console
        self.progress: Progress = RichProgress(
            SpinnerColumn(style="green"),
            TextColumn("{task.description}", markup=False, table_column=Column(width=LABEL_WIDTH)),
            Bar(),
            Amount(),
            TimeElapsedColumn(),
            console=console,
            refresh_per_second=REFRESH,
        )

    def __enter__(self) -> "LiveTracker":
        self.progress.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.progress.stop()

    def step(self, label: str, total: int | None = None, unit: str = "") -> "_LiveStep":
        return _LiveStep(self, self.progress.add_task(label, total=total, unit=unit), label)

    def record(self, mark: str, style: str, label: str, note: str, took: str | None) -> None:
        """A finished step's permanent line: mark, label, note, and the time at the right edge."""
        from rich.table import Table
        from rich.text import Text

        line = Table.grid(expand=True, padding=(0, 1))
        line.add_column(width=1)
        line.add_column(width=LABEL_WIDTH, no_wrap=True)
        line.add_column(ratio=1)
        line.add_column(justify="right")
        line.add_row(
            Text(mark, style=f"bold {style}"),
            Text(label, style="bold"),
            Text(note, style=style if style == "red" else ""),
            Text(took or "", style="dim"),
        )
        self.console.print(line)


class _LiveStep:
    def __init__(self, tracker: LiveTracker, task: "TaskID", label: str) -> None:
        self._tracker, self._task, self._label = tracker, task, label
        self._start = time.monotonic()

    def update(self, done: int, total: int | None = None) -> None:
        self._tracker.progress.update(self._task, completed=done, total=total)

    def _end(self) -> str:
        self._tracker.progress.remove_task(self._task)
        return elapsed(time.monotonic() - self._start)

    def ok(self, note: str = "") -> None:
        self._tracker.record("✔", "green", self._label, note, self._end())

    def fail(self, why: str) -> None:
        self._tracker.record("✘", "red", self._label, why, self._end())

    def drop(self) -> None:
        self._tracker.progress.remove_task(self._task)


# ---- choosing -----------------------------------------------------------------------------


@contextmanager
def open_tracker(title: str) -> Iterator[Tracker]:
    """The live display on a terminal, plain lines anywhere else. title names the run
    in the plain header (the scheduled job's log gets one line per run with the date)."""
    if sys.stdout.isatty():
        from rich.console import Console

        console = Console()
        if console.is_terminal and not console.is_dumb_terminal:
            with LiveTracker(console) as live:
                yield live
            return
    log = LogTracker()
    log.header(title)
    yield log
