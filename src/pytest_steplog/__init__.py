"""pytest-steplog: structured step metadata, retry/attempt tracking and
resume-on-retry for pytest, with a pluggable custom-record extension system.
"""

from __future__ import annotations

from pytest_steplog.collector import StepLogCollector
from pytest_steplog.models import LogRecord, Run, Step
from pytest_steplog.registry import RecordSpec, steplog_record

__all__ = [
    "StepLogCollector",
    "LogRecord",
    "Run",
    "Step",
    "RecordSpec",
    "steplog_record",
]

__version__ = "0.1.0"
