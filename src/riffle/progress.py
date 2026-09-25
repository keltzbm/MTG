"""Progress for long-running work, shown while it happens.

Ingest code reports through a Tracker and never draws anything itself: it
opens a step, updates it with a count (or bytes) as work proceeds, and ends it
with ok(note), fail(why), or drop() when there's nothing worth recording.

The CLI picks the display with open_tracker(). On a terminal, Rich draws a
line per running step: a spinner, a bar with the count or bytes and speed, and
the time so far. A finished step turns into a permanent line, a green ✔ (or a
red ✘) with its note and how long it took, printed in order with everything
else the command says. Anywhere else, notably the scheduled job's sync.log,
nothing animates: a dated line when the run starts, then a timestamped line as
each step ends.
"""

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


class LiveTracker:
    """Running steps redrawn in place; finished steps printed as permanent lines.

    Everything else printed while it's open (typer.echo included) appears above
    the running steps, because Rich redirects stdout and stderr meanwhile.
    """

    def __init__(self, console: "Console") -> None:
        from rich.progress import BarColumn, ProgressColumn, SpinnerColumn, TextColumn, TimeElapsedColumn
        from rich.progress import Progress as RichProgress
        from rich.table import Column

        class Amount(ProgressColumn):
            def render(self, task: "Task") -> "Text":
                return _amount(task)

        self.console = console
        self.progress: Progress = RichProgress(
            SpinnerColumn(style="green"),
            TextColumn("{task.description}", markup=False, table_column=Column(width=LABEL_WIDTH)),
            BarColumn(bar_width=28, complete_style="green", finished_style="green", pulse_style="green"),
            Amount(),
            TimeElapsedColumn(),
            console=console,
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
