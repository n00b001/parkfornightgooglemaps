"""
Dual-output logging: Rich console + plain text log file.

Progress bars render to terminal (Rich).
Plain text progress updates written to log file periodically
so you can tail the log and see progress.

Why progress bars must be in the log file too:
  When running the pipeline in the background (tmux, cron, etc.),
  you can't see the Rich progress bars. The log file is the only
  way to monitor progress. Every logger.info() goes to both
  console and file automatically.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import UTC, datetime
from typing import Any

from rich.console import Console
from rich.logging import RichHandler
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.progress import (
    Progress as RichProgress,
)

# Force terminal rendering even when piped
console = Console(force_terminal=True, soft_wrap=False)

logger: logging.Logger | None = None
_log_file_path: str = ""


def setup_logging(log_dir: str) -> tuple[logging.Logger, str]:
    """Configure logging with dual output: console + timestamped log file.

    All log messages have timestamps in the file.
    Console output uses Rich formatting (colors, progress bars).
    File output uses plain text with timestamps.

    Args:
        log_dir: Directory to write log files to.

    Returns:
        (logger, log_file_path)
    """
    global logger, _log_file_path

    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"pipeline_{timestamp}.log")
    _log_file_path = log_file

    # Console handler with Rich formatting
    console_handler = RichHandler(
        console=console,
        show_time=True,
        show_level=False,
        markup=False,
    )
    console_handler.setFormatter(logging.Formatter("%(message)s"))

    # File handler for detailed logging with timestamps
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)-8s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    logger = logging.getLogger("pipeline")
    logger.setLevel(logging.INFO)
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    console.print(f"  Log file: [cyan]{log_file}[/cyan]")
    return logger, log_file


def get_logger() -> logging.Logger | None:
    """Get the global logger instance."""
    return logger


def get_log_file_path() -> str:
    """Get the current log file path."""
    return _log_file_path


def log_progress(
    phase: str,
    completed: int,
    total: int,
    extra: str = "",
) -> None:
    """Write progress update to log file (visible when tailing).

    Call this periodically inside your loop to keep the log updated.
    Progress bars on the console are visual only — this function
    ensures the log file has the same information in plain text.

    Args:
        phase: Name of the phase (e.g. 'Extracting places').
        completed: Number of items completed so far.
        total: Total number of items.
        extra: Additional info to append (e.g. '12.5 places/s').
    """
    if logger:
        pct = (completed / total * 100) if total else 0
        msg = f"[{phase}] {completed:>8,}/{total:,} ({pct:5.1f}%)"
        if extra:
            msg += f" • {extra}"
        logger.info(msg)


def create_progress(
    description: str,
    total: int | None = None,
    **kwargs: Any,
) -> RichProgress:
    """Create a Rich Progress context manager.

    Creates a progress bar with spinner, description, bar, completion
    count, elapsed time, and ETA (when total is known).

    Args:
        description: Task label shown in the progress bar.
        total: Total number of items (None for indeterminate spinner).

    Returns:
        A Rich Progress object to use as a context manager.
    """
    columns: list[Any] = [
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
    ]

    if total is not None:
        columns.extend(
            [
                BarColumn(),
                MofNCompleteColumn(),
                TextColumn("•"),
                TimeElapsedColumn(),
                TextColumn("•"),
                TimeRemainingColumn(),
            ]
        )

    if logger:
        logger.info(f"▶ {description}")

    return RichProgress(*columns, console=console, **kwargs)


class ProgressTracker:
    """Track progress and log to file at regular intervals.

    Use this to ensure progress is logged to the file even when
    the console progress bar is updating rapidly.

    Example:
        tracker = ProgressTracker("Processing places", total=1000)
        for i, place in enumerate(places):
            process(place)
            tracker.update(i + 1)
        tracker.finish()
    """

    def __init__(
        self,
        phase: str,
        total: int,
        interval: float = 5.0,
    ) -> None:
        """Create a progress tracker.

        Args:
            phase: Name of the phase for log messages.
            total: Total number of items.
            interval: Minimum seconds between log updates.
        """
        self.phase = phase
        self.total = total
        self.interval = interval
        self.completed = 0
        self.last_log_time = 0.0
        self.start_time = time.time()

    def update(self, completed: int, extra: str = "") -> None:
        """Update progress. Logs to file if enough time has passed.

        Args:
            completed: Number of items completed so far.
            extra: Additional info to append to log message.
        """
        self.completed = completed
        now = time.time()
        if now - self.last_log_time >= self.interval:
            elapsed = now - self.start_time
            rate = completed / elapsed if elapsed > 0 else 0
            rate_str = f"{rate:.1f}/s" if rate > 0 else ""
            log_progress(self.phase, completed, self.total, extra or rate_str)
            self.last_log_time = now

    def finish(self) -> None:
        """Log final progress and elapsed time."""
        elapsed = time.time() - self.start_time
        rate = self.completed / elapsed if elapsed > 0 else 0
        rate_str = f"{rate:.1f}/s" if rate > 0 else ""
        log_progress(self.phase, self.completed, self.total, rate_str)
        if logger:
            logger.info(f"✓ {self.phase} complete: {self.completed:,} items in {elapsed:.1f}s")
