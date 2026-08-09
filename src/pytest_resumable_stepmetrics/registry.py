"""Custom-record extension system for pytest-resumable-stepmetrics.

Users register their own dataclasses with :func:`steplog_record` (or just pass
any dataclass to ``steplog.record``) to attach domain-specific, per-attempt
records to a test.  Registered records are serialised into the JSON report and
rendered as their own terminal table with zero extra code.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Any, Callable

# type -> RecordSpec, populated by the ``steplog_record`` decorator.
_REGISTRY: dict[type, "RecordSpec"] = {}

_CAMEL_RE = re.compile(r"(?<!^)(?=[A-Z])")


def _snake(name: str) -> str:
    """Convert a class name to a snake_case report key.

    Args:
        name: Class name, e.g. ``CollateralAction``.

    Returns:
        str: snake_case name, e.g. ``collateral_action``.

    """

    return _CAMEL_RE.sub("_", name).lower()


@dataclasses.dataclass
class RecordSpec:
    """Registration metadata for a custom record type.

    Attributes:
        key: Report section name (JSON key and table title).
        stamp: Field names the framework fills from the collector context on
            every ``record`` call (e.g. ``attempt``, ``run_id``).
        render: Optional callable taking the list of records and returning a
            string table.  When ``None`` a default table is auto-generated.

    """

    key: str
    stamp: tuple[str, ...] = ()
    render: Callable[[list[Any]], str] | None = None

    @classmethod
    def default_for(cls, record_type: type) -> "RecordSpec":
        """Build a default spec for an unregistered dataclass.

        Args:
            record_type: The record's class.

        Returns:
            RecordSpec: A spec using the snake_case class name as the key.

        """

        return cls(key=_snake(record_type.__name__))


def steplog_record(
    _cls: type | None = None,
    *,
    key: str | None = None,
    stamp: tuple[str, ...] | str = (),
    render: Callable[[list[Any]], str] | None = None,
):
    """Register a dataclass as a steplog custom record type.

    Can be used bare (``@steplog_record``) or with arguments
    (``@steplog_record(key=..., stamp=...)``).

    Args:
        _cls: The class, when used as a bare decorator.
        key: Report section name.  Defaults to the snake_case class name.
        stamp: Field name(s) auto-filled from the collector context on each
            ``record`` call.  A single name may be given as a string.
        render: Optional custom table renderer.

    Returns:
        The decorated class (unchanged), or a decorator when called with args.

    Raises:
        TypeError: If applied to a non-dataclass.

    """

    stamp_tuple = (stamp,) if isinstance(stamp, str) else tuple(stamp)

    def wrap(cls: type) -> type:
        if not dataclasses.is_dataclass(cls):
            raise TypeError(
                f"steplog_record can only decorate dataclasses; got {cls!r}"
            )
        _REGISTRY[cls] = RecordSpec(
            key=key or _snake(cls.__name__),
            stamp=stamp_tuple,
            render=render,
        )
        return cls

    if _cls is not None:
        return wrap(_cls)
    return wrap


def spec_for(record_type: type) -> RecordSpec:
    """Return the registered spec for a type, or a sensible default.

    Args:
        record_type: The record's class.

    Returns:
        RecordSpec: The registered or default spec.

    """

    return _REGISTRY.get(record_type) or RecordSpec.default_for(record_type)
