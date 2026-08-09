"""Reporting: terminal tables and JSON serialisation for pytest-resumable-stepmetrics."""

from __future__ import annotations

import dataclasses
from typing import Any

from pytest_resumable_stepmetrics.collector import StepLogCollector
from pytest_resumable_stepmetrics.models import Step
from pytest_resumable_stepmetrics.registry import spec_for


def _render_table(headers: list[str], rows: list[list[Any]]) -> str:
    """Render a simple, dependency-free ASCII table.

    Args:
        headers: Column headers.
        rows: Row values (each a list aligned with ``headers``).

    Returns:
        str: The formatted table.

    """

    cols = [headers] + [[str(c) for c in r] for r in rows]
    widths = [
        max(len(str(cols[r][i])) for r in range(len(cols))) for i in range(len(headers))
    ]

    def line(char: str) -> str:
        return "+" + "+".join(char * (w + 2) for w in widths) + "+"

    def fmt(values: list[Any]) -> str:
        return (
            "| "
            + " | ".join(str(v).ljust(widths[i]) for i, v in enumerate(values))
            + " |"
        )

    out = [line("-"), fmt(headers), line("=")]
    out += [fmt(r) for r in rows]
    out.append(line("-"))
    return "\n".join(out)


def render_steps_table(steps: list[Step]) -> str:
    """Render the per-step summary table.

    An ``Attempt`` column is shown automatically when any step ran on a retry.

    Args:
        steps: The steps to summarise.

    Returns:
        str: The formatted table (empty string if no steps).

    """

    if not steps:
        return ""
    show_attempt = any(s.attempt > 1 for s in steps)
    headers = ["#", "Step"]
    if show_attempt:
        headers.append("Attempt")
    headers += ["Status", "Duration(s)", "Errors", "Warnings", "Info"]
    rows: list[list[Any]] = []
    for i, s in enumerate(steps, start=1):
        errors = sum(1 for log in s.logs if log.level in ("ERROR", "CRITICAL"))
        warnings = sum(1 for log in s.logs if log.level == "WARNING")
        info = sum(1 for log in s.logs if log.level == "INFO")
        row: list[Any] = [i, s.name]
        if show_attempt:
            row.append(s.attempt)
        row += [s.status, f"{(s.duration_seconds or 0):.3f}", errors, warnings, info]
        rows.append(row)
    return _render_table(headers, rows)


def render_records_table(records: list[Any]) -> str:
    """Auto-render a table for a list of same-typed dataclass records.

    Uses the registered custom renderer if one was provided.

    Args:
        records: Records of a single dataclass type.

    Returns:
        str: The formatted table (empty string if no records).

    """

    if not records:
        return ""
    spec = spec_for(type(records[0]))
    if spec.render is not None:
        return spec.render(records)
    fields = [f.name for f in dataclasses.fields(records[0])]
    headers = [f.replace("_", " ").title() for f in fields]
    rows = [[getattr(r, f) for f in fields] for r in records]
    return _render_table(headers, rows)


def to_json_dict(collector: StepLogCollector) -> dict[str, Any]:
    """Serialise a collector into a JSON-ready dictionary.

    Each registered custom-record type is written under its own key.

    Args:
        collector: The collector to serialise.

    Returns:
        dict: ``{"run", "steps", <record-key>...}``.

    """

    result: dict[str, Any] = {
        "run": dataclasses.asdict(collector.run),
        "steps": [
            {k: v for k, v in dataclasses.asdict(s).items() if k != "logs"}
            for s in collector.steps
        ],
    }
    for record_type, items in collector.records.items():
        spec = spec_for(record_type)
        result[spec.key] = [dataclasses.asdict(x) for x in items]
    return result
