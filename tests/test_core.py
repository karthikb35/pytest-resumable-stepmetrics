"""Unit tests for the pytest-steplog collector, registry and reporter."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from pytest_steplog import steplog_record
from pytest_steplog.collector import StepLogCollector
from pytest_steplog.registry import spec_for
from pytest_steplog.reporter import render_records_table, render_steps_table, to_json_dict


def test_step_status_capture():
    c = StepLogCollector("t")
    with c.track_step("ok"):
        pass
    with pytest.raises(RuntimeError):
        with c.track_step("boom"):
            raise RuntimeError("x")
    statuses = {s.name: s.status for s in c.steps}
    assert statuses == {"ok": "passed", "boom": "failed"}


def test_retry_count_and_attempt_stamping():
    c = StepLogCollector("t")
    c.reset_attempt()  # attempt 1
    with c.track_step("a"):
        pass
    c.reset_attempt()  # retry 1
    with c.track_step("a2"):
        pass
    c.reset_attempt()  # retry 2
    assert c.run.retry_count == 2
    assert c.steps[0].attempt == 1
    assert c.steps[1].attempt == 2


def test_resumable_skips_after_success():
    c = StepLogCollector("t")
    ran = []

    def attempt():
        c.reset_attempt()
        with c.resumable_step("download") as step:
            if not step.resumed:
                ran.append(c._attempt)
        with c.track_step("flash") as step:
            if c._attempt < 2:
                raise RuntimeError("flash failed")

    with pytest.raises(RuntimeError):
        attempt()
    attempt()

    assert ran == [1], "download should run only once"
    download_steps = [s for s in c.steps if s.name == "download"]
    assert download_steps[0].resumed is False
    assert download_steps[1].resumed is True
    assert download_steps[1].status == "skipped"


def test_resumable_reruns_on_failure():
    c = StepLogCollector("t")
    ran = []

    def attempt(fail: bool):
        c.reset_attempt()
        with c.track_step("download") as step:  # not resumable here for clarity
            pass
        with c.resumable_step("verify") as step:
            if not step.resumed:
                ran.append(c._attempt)
                if fail:
                    raise RuntimeError("verify failed")

    with pytest.raises(RuntimeError):
        attempt(fail=True)
    attempt(fail=False)
    assert ran == [1, 2], "verify should re-run because it failed the first time"


def test_record_without_registration_uses_defaults():
    @dataclass
    class Thing:
        kind: str
        detail: str = ""

    c = StepLogCollector("t")
    c.record(Thing(kind="reset", detail="power cycle"))
    assert spec_for(Thing).key == "thing"
    assert to_json_dict(c)["thing"] == [{"kind": "reset", "detail": "power cycle"}]


def test_record_stamps_attempt_from_context():
    @steplog_record(key="collateral_actions", stamp=("attempt",))
    @dataclass
    class CollateralAction:
        component: str
        action: str
        attempt: int = 1

    c = StepLogCollector("t")
    c.reset_attempt()  # attempt 1
    c.record(CollateralAction("bmc", "flashed"))
    c.reset_attempt()  # attempt 2
    c.record(CollateralAction("bios", "flashed"))

    actions = c.records_of(CollateralAction)
    assert [a.attempt for a in actions] == [1, 2]
    report = to_json_dict(c)
    assert report["collateral_actions"][0]["component"] == "bmc"


def test_record_rejects_non_dataclass():
    c = StepLogCollector("t")
    with pytest.raises(TypeError):
        c.record({"not": "a dataclass"})


def test_steplog_record_rejects_non_dataclass():
    with pytest.raises(TypeError):

        @steplog_record
        class NotADataclass:
            pass


def test_render_tables_are_non_empty():
    @dataclass
    class Row:
        a: str
        b: int

    c = StepLogCollector("t")
    with c.track_step("s"):
        pass
    c.record(Row(a="x", b=1))
    assert "Step" in render_steps_table(c.steps)
    assert "x" in render_records_table(c.records_of(Row))
