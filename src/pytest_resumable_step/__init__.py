"""pytest-resumable-step: structured step metadata, retry/attempt tracking and
resume-on-retry for pytest, with a pluggable custom-record extension system.
"""

from __future__ import annotations

from pytest_resumable_step.collector import StepLogCollector
from pytest_resumable_step.models import LogRecord, Run, Step
from pytest_resumable_step.registry import RecordSpec, steplog_record

__all__ = [
    "StepLogCollector",
    "LogRecord",
    "Run",
    "Step",
    "RecordSpec",
    "steplog_record",
]

__version__ = "0.1.0"
