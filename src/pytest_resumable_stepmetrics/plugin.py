"""Pytest plugin entry point: the ``steplog`` fixture and reporting hooks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Generator

import pytest

from pytest_resumable_stepmetrics.collector import StepLogCollector
from pytest_resumable_stepmetrics.registry import spec_for
from pytest_resumable_stepmetrics.reporter import (
    render_records_table,
    render_steps_table,
    to_json_dict,
)

_results_key: pytest.StashKey[list] = pytest.StashKey()
_outcome_key: pytest.StashKey[str] = pytest.StashKey()


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register command-line options.

    Args:
        parser: The pytest option parser.

    """

    group = parser.getgroup("steplog")
    group.addoption(
        "--steplog-json",
        action="store_true",
        default=False,
        help="Write a report.json into each test's log directory.",
    )
    group.addoption(
        "--steplog-json-dir",
        action="store",
        default=None,
        help="Directory for per-test report.json files (default: .steplog).",
    )


class _StepFactory:
    """Callable returned by the ``steplog`` fixture.

    Calling it tracks a step; it also exposes ``.collector``, ``.resumable``,
    ``.record`` and ``.reset_attempt`` helpers.
    """

    def __init__(self, collector: StepLogCollector) -> None:
        self.collector = collector

    def __call__(self, name: str):
        """Track a step by name.

        Args:
            name: The step name.

        Returns:
            A context manager yielding the :class:`Step`.

        """

        return self.collector.track_step(
            name, skip_exceptions=(pytest.skip.Exception,)
        )

    def resumable(self, name: str):
        """Track a resumable (skip-on-retry) step.

        Args:
            name: The step name.

        Returns:
            A context manager yielding the :class:`Step`.

        """

        return self.collector.resumable_step(
            name, skip_exceptions=(pytest.skip.Exception,)
        )

    def run(self, name: str, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """Track a step and skip *calling* ``func`` on retry once it has passed.

        The guard-free counterpart to :meth:`resumable` — ``func`` is simply not
        invoked when the step already succeeded, so no ``if not step.resumed``
        check is needed. See :meth:`StepLogCollector.run_step`.

        Args:
            name: The step name.
            func: Callable performing the step's work.
            *args: Positional arguments forwarded to ``func``.
            **kwargs: Keyword arguments forwarded to ``func``.

        Returns:
            Whatever ``func`` returns, or ``None`` if the step was skipped.

        """

        return self.collector.run_step(name, func, *args, **kwargs)

    def record(self, obj: Any) -> Any:
        """Attach a custom dataclass record. See :meth:`StepLogCollector.record`.

        Args:
            obj: A dataclass instance.

        Returns:
            The stored record.

        """

        return self.collector.record(obj)

    def reset_attempt(self) -> None:
        """Advance the attempt counter (call first inside a retry loop)."""

        self.collector.reset_attempt()

    @property
    def context(self) -> dict[str, Any]:
        """Mutable context dict used to auto-stamp custom records."""

        return self.collector.context


@pytest.fixture
def steplog(request: pytest.FixtureRequest) -> Generator[_StepFactory, None, None]:
    """Per-test step tracker with metadata, retry and custom-record support.

    Args:
        request: The pytest fixture request.

    Yields:
        _StepFactory: The step factory / API surface.

    """

    collector = StepLogCollector(test_nodeid=request.node.nodeid)
    collector.attach_logging()
    factory = _StepFactory(collector)

    yield factory

    outcome = request.node.stash.get(_outcome_key, None)
    collector.end_run(outcome)
    collector.detach_logging()

    if request.config.getoption("--steplog-json"):
        base = request.config.getoption("--steplog-json-dir") or ".steplog"
        safe = request.node.nodeid.replace("/", "_").replace("::", "__")
        out_dir = Path(str(request.config.rootpath)) / base
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{safe}.json").write_text(
            json.dumps(to_json_dict(collector), indent=2, default=str),
            encoding="utf-8",
        )

    request.config.stash[_results_key].append(collector)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo
) -> Generator[None, None, None]:
    """Capture each test's call-phase outcome for the fixture teardown.

    Args:
        item: The test item.
        call: The call info for the current phase.

    """

    outcome = yield
    rep = outcome.get_result()
    if call.when == "call":
        item.stash[_outcome_key] = (
            "skipped" if rep.skipped else ("failed" if rep.failed else "passed")
        )
    elif call.when == "setup" and (rep.failed or rep.skipped):
        item.stash[_outcome_key] = "skipped" if rep.skipped else "failed"


def pytest_sessionstart(session: pytest.Session) -> None:
    """Initialise the per-session results store.

    Args:
        session: The pytest session.

    """

    session.config.stash[_results_key] = []


@pytest.hookimpl(trylast=True)
def pytest_terminal_summary(terminalreporter: Any, config: pytest.Config) -> None:
    """Print per-test step and custom-record summaries.

    Args:
        terminalreporter: The terminal reporter.
        config: The pytest config.

    """

    results: list[StepLogCollector] = config.stash.get(_results_key, [])
    if not results:
        return

    terminalreporter.write_line("\nsteplog summary:")
    for collector in results:
        if not collector.steps and not collector.records:
            continue
        terminalreporter.write_sep("=", "=")
        terminalreporter.write_line(f"  Test:    {collector.run.test_nodeid}")
        terminalreporter.write_line(f"  Status:  {collector.run.status.upper()}")
        if collector.run.retry_count:
            terminalreporter.write_line(f"  Retries: {collector.run.retry_count}")
        if collector.steps:
            terminalreporter.write_line("\n Steps:")
            terminalreporter.write_line(render_steps_table(collector.steps))
        for record_type, items in collector.records.items():
            terminalreporter.write_line(f"\n {spec_for(record_type).key}:")
            terminalreporter.write_line(render_records_table(items))
        terminalreporter.write_line("")
