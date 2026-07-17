"""Core data models for pytest-resumable-step."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC ``datetime``.

    Returns:
        datetime: The current UTC time.

    """

    return datetime.now(timezone.utc)


def _parse_iso(timestamp: str) -> datetime:
    """Parse an ISO 8601 timestamp, tolerating a trailing ``Z``.

    Args:
        timestamp: ISO 8601 timestamp string.

    Returns:
        datetime: The parsed timezone-aware datetime.

    """

    return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


@dataclass
class LogRecord:
    """A single captured logging event.

    Attributes:
        timestamp: ISO 8601 time the record was emitted.
        logger: Name of the logger that produced the record.
        level: Log level name (e.g. ``INFO``, ``ERROR``).
        message: Formatted log message.

    """

    timestamp: str
    logger: str
    level: str
    message: str


@dataclass
class Step:
    """A tracked step within a test.

    Attributes:
        name: Human-readable step name.
        attempt: 1-based attempt index (``1`` on the first run, higher on retries).
        resumed: ``True`` when the step body was skipped on a retry because it
            already succeeded on an earlier attempt.
        status: ``running``, ``passed``, ``failed`` or ``skipped``.
        started_at: ISO 8601 start time.
        ended_at: ISO 8601 end time, or ``None`` while running.
        duration_seconds: Elapsed seconds, or ``None`` until closed.
        error: Error text if the step failed, otherwise ``None``.
        info: Arbitrary user-supplied metadata for the step.
        logs: Ordered log records captured while the step was current.

    """

    name: str
    attempt: int = 1
    resumed: bool = False
    status: str = "running"
    started_at: str = field(default_factory=lambda: utc_now().isoformat())
    ended_at: str | None = None
    duration_seconds: float | None = None
    error: str | None = None
    info: dict[str, Any] = field(default_factory=dict)
    logs: list[LogRecord] = field(default_factory=list)

    def close(self, status: str, error: str | None = None) -> None:
        """Finalise the step with a status and optional error.

        Args:
            status: Final status string.
            error: Optional error message.

        """

        ended = utc_now()
        self.ended_at = ended.isoformat()
        self.duration_seconds = (ended - _parse_iso(self.started_at)).total_seconds()
        self.status = status
        self.error = error or None


@dataclass
class Run:
    """Summary of a single test's run lifecycle.

    Attributes:
        test_nodeid: Pytest node id of the test.
        status: ``running``, ``passed``, ``failed`` or ``skipped``.
        started_at: ISO 8601 start time.
        ended_at: ISO 8601 end time, or ``None`` while running.
        duration_seconds: Elapsed seconds, or ``None`` until closed.
        retry_count: Number of retries after the initial attempt (``0`` if none).
        info: Arbitrary user-supplied run-level metadata.

    """

    test_nodeid: str
    status: str = "running"
    started_at: str = field(default_factory=lambda: utc_now().isoformat())
    ended_at: str | None = None
    duration_seconds: float | None = None
    retry_count: int = 0
    info: dict[str, Any] = field(default_factory=dict)

    def close(self, status: str) -> None:
        """Finalise the run with a status.

        Args:
            status: Final status string.

        """

        ended = utc_now()
        self.ended_at = ended.isoformat()
        self.duration_seconds = (ended - _parse_iso(self.started_at)).total_seconds()
        self.status = status
