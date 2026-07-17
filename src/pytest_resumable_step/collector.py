"""Collector: step tracking, retry/attempt bookkeeping, and custom records."""

from __future__ import annotations

import contextlib
import contextvars
import dataclasses
import logging
from typing import Any, Generator

from pytest_resumable_step.models import LogRecord, Run, Step, utc_now
from pytest_resumable_step.registry import spec_for

_CURRENT_STEP: contextvars.ContextVar["Step | None"] = contextvars.ContextVar(
    "steplog_current_step", default=None
)


class _CollectorHandler(logging.Handler):
    """Logging handler that attaches records to the currently-tracked step."""

    def emit(self, record: logging.LogRecord) -> None:
        """Append a log record to the current step, if any.

        Args:
            record: The emitted logging record.

        """

        step = _CURRENT_STEP.get()
        if step is None:
            return
        step.logs.append(
            LogRecord(
                timestamp=utc_now().isoformat(),
                logger=record.name,
                level=record.levelname,
                message=record.getMessage(),
            )
        )


class StepLogCollector:
    """Tracks a single test's steps, attempts and custom records."""

    def __init__(self, test_nodeid: str = "unknown") -> None:
        """Initialise the collector.

        Args:
            test_nodeid: Pytest node id of the test being tracked.

        """

        self.run = Run(test_nodeid=test_nodeid)
        self.steps: list[Step] = []
        self.records: dict[type, list[Any]] = {}
        self.context: dict[str, Any] = {"attempt": 1, "test_nodeid": test_nodeid}
        self._handler = _CollectorHandler()
        self._attached = False
        self._attempt = 0
        self._completed: set[str] = set()

    # ── logging capture ───────────────────────────────────────────────────────
    def attach_logging(self) -> None:
        """Start capturing root-logger records into the current step."""

        if not self._attached:
            logging.getLogger().addHandler(self._handler)
            self._attached = True

    def detach_logging(self) -> None:
        """Stop capturing root-logger records."""

        if self._attached:
            logging.getLogger().removeHandler(self._handler)
            self._attached = False

    # ── attempt / retry bookkeeping ───────────────────────────────────────────
    def reset_attempt(self) -> None:
        """Advance the attempt counter before a (re)try.

        Call as the first statement of every attempt (including the first).
        ``_attempt`` is incremented on every call; ``run.retry_count`` is only
        incremented from the second call onward (the first call is not a retry).
        The set of completed resumable steps is intentionally retained across
        attempts so resume-on-retry works.

        """

        if self._attempt > 0:
            self.run.retry_count += 1
        self._attempt += 1
        self.context["attempt"] = max(1, self._attempt)

    # ── step tracking ─────────────────────────────────────────────────────────
    @contextlib.contextmanager
    def track_step(
        self,
        name: str,
        skip_exceptions: tuple[type[BaseException], ...] = (),
    ) -> Generator[Step, None, None]:
        """Track a step lifecycle via a context manager.

        Args:
            name: Human-readable step name.
            skip_exceptions: Exception types that mark the step ``skipped``
                instead of ``failed``.

        Yields:
            Step: The step model for the duration of the block.

        Raises:
            BaseException: Re-raises whatever the body raised, after recording.

        """

        step = Step(name=name, attempt=max(1, self._attempt))
        self.steps.append(step)
        token = _CURRENT_STEP.set(step)
        try:
            yield step
        except skip_exceptions as exc:
            if step.status == "running":
                step.close("skipped", error=str(exc))
            raise
        except BaseException as exc:  # noqa: BLE001 - re-raised below
            if step.status == "running":
                step.close("failed", error=str(exc))
            raise
        else:
            if step.status == "running":
                step.close("passed")
            elif step.status not in ("passed", "failed", "skipped"):
                step.close(step.status)
        finally:
            _CURRENT_STEP.reset(token)

    @contextlib.contextmanager
    def resumable_step(
        self,
        name: str,
        skip_exceptions: tuple[type[BaseException], ...] = (),
    ) -> Generator[Step, None, None]:
        """Track a step that is *skipped on retry* once it has succeeded.

        Use only for pure / idempotent steps whose side effects persist across
        retries (downloads, resolution, hashing).  Do **not** use it for
        stateful steps that must re-run to re-establish a known-good state.

        Guard the body with the yielded step's ``resumed`` flag::

            with steplog.resumable("download") as step:
                if not step.resumed:
                    ...expensive work...

        Args:
            name: Stable step name.
            skip_exceptions: Exception types that mark the step ``skipped``.

        Yields:
            Step: The step model; ``resumed`` is ``True`` when skipped.

        """

        if name in self._completed:
            step = Step(name=name, attempt=max(1, self._attempt), resumed=True)
            step.info["resumed"] = True
            self.steps.append(step)
            step.close("skipped")
            yield step
            return

        with self.track_step(name, skip_exceptions=skip_exceptions) as step:
            yield step
        if step.status == "passed":
            self._completed.add(name)

    def run_step(self, name: str, func, *args, **kwargs):
        """Track a step and *skip calling* ``func`` on retry once it has passed.

        Unlike :meth:`resumable_step`, ``func`` is only invoked when the step
        has not already succeeded — so the expensive work is genuinely skipped
        with **no guard** needed in caller code (a ``with`` block always runs
        its body, but a callable can simply not be called).

        Use only for pure / idempotent work whose effects survive a retry.

        Args:
            name: Stable step name.
            func: Callable performing the step's work.
            *args: Positional arguments forwarded to ``func``.
            **kwargs: Keyword arguments forwarded to ``func``.

        Returns:
            Whatever ``func`` returns, or ``None`` if the step was skipped.

        """

        if name in self._completed:
            step = Step(name=name, attempt=max(1, self._attempt), resumed=True)
            step.info["resumed"] = True
            self.steps.append(step)
            step.close("skipped")
            return None

        with self.track_step(name) as step:
            result = func(*args, **kwargs)
        if step.status == "passed":
            self._completed.add(name)
        return result

    # ── custom records ────────────────────────────────────────────────────────
    def record(self, obj: Any) -> Any:
        """Attach a custom dataclass record to this test.

        Fields declared in the record type's ``stamp`` spec are filled from the
        collector context (e.g. ``attempt``) before the record is stored.

        Args:
            obj: A dataclass instance (optionally registered via
                :func:`~pytest_resumable_step.registry.steplog_record`).

        Returns:
            The stored record instance.

        Raises:
            TypeError: If ``obj`` is not a dataclass instance.

        """

        if not dataclasses.is_dataclass(obj) or isinstance(obj, type):
            raise TypeError(
                f"steplog.record() requires a dataclass instance; got {obj!r}"
            )
        spec = spec_for(type(obj))
        valid = {f.name for f in dataclasses.fields(obj)}
        for name in spec.stamp:
            if name in valid and name in self.context:
                setattr(obj, name, self.context[name])
        self.records.setdefault(type(obj), []).append(obj)
        return obj

    def records_of(self, record_type: type) -> list[Any]:
        """Return all stored records of a given type.

        Args:
            record_type: The record's class.

        Returns:
            list: Stored records of that type (empty if none).

        """

        return self.records.get(record_type, [])

    # ── finalisation ──────────────────────────────────────────────────────────
    def end_run(self, outcome: str | None) -> None:
        """Close the run, deriving a final status.

        Args:
            outcome: Pytest call outcome (``passed``/``failed``/``skipped``) or
                ``None`` (treated as ``failed``).

        """

        if self.run.status != "running":
            return
        self.run.close(outcome if outcome in {"passed", "failed", "skipped"} else "failed")
