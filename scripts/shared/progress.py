"""Shared progress bar utilities for all scripts.

Provides dual-output progress: rich Progress on console + plain text in log file.
Import this from any script to get consistent, loggable progress bars.

Usage:
    from shared.progress import ProgressLogger

    pl = ProgressLogger(logger)
    with pl.progress("Processing items", total=10000) as task:
        for i, item in enumerate(items):
            process(item)
            pl.advance(task, 1)
"""

from __future__ import annotations

import logging

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress as RichProgress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

# Force terminal rendering even when piped
console = Console(force_terminal=True, soft_wrap=False)


class ProgressLogger:
    """Dual-output progress bar: rich console + plain text log file."""

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger

    def _log(self, message: str) -> None:
        """Write to log file (visible when tailing)."""
        if self.logger:
            self.logger.info(message)

    def progress(
        self,
        description: str,
        total: int | None = None,
    ) -> RichProgress:
        """Create a rich Progress context manager.

        Args:
            description: Task label shown in the progress bar.
            total: Total number of items (None for indeterminate spinner).

        Returns:
            A Rich Progress object to use as a context manager.
        """
        columns = [
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

        self._log(f"▶ {description}")
        return RichProgress(*columns, console=console)

    def advance(self, task: int, step: int = 1) -> None:
        """Advance a progress task by the given step."""
        # No-op — progress is advanced via the Rich Progress object directly
        pass

    def update(
        self,
        phase: str,
        completed: int,
        total: int,
        extra: str = "",
    ) -> None:
        """Write a progress update to the log file.

        Call this periodically inside your loop to keep the log updated.
        """
        pct = (completed / total * 100) if total else 0
        msg = f"[{phase}] {completed:>8,}/{total:,} ({pct:5.1f}%)"
        if extra:
            msg += f" • {extra}"
        self._log(msg)

    def done(self, phase: str, count: int) -> None:
        """Log completion of a phase."""
        self._log(f"✓ {phase}: {count:,} items")
