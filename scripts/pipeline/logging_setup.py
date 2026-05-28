"""
Dual-output logging: Rich console + plain text log file.

Progress bars render to terminal (Rich).
Plain text progress updates written to log file periodically
so you can tail the log and see progress.
"""

from __future__ import annotations

import logging
import os
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


def log_progress(phase: str, completed: int, total: int) -> None:
    """Write progress update to log file (visible when tailing).

    Call this periodically inside your loop to keep the log updated.
    """
    if logger:
        pct = (completed / total * 100) if total else 0
        logger.info(f"[{phase}] {completed:>8,}/{total:,} ({pct:5.1f}%)")


def create_progress(
    description: str,
    total: int | None = None,
    **kwargs: Any,
) -> RichProgress:
    """Create a Rich Progress context manager.

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
            ]
        )

    if logger:
        logger.info(f"▶ {description}")

    return RichProgress(*columns, console=console, **kwargs)
