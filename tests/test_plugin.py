"""End-to-end tests that run pytest-in-pytest via the pytester fixture."""

from __future__ import annotations


def test_fixture_available_and_json_written(pytester):
    pytester.makepyfile(
        """
        from dataclasses import dataclass
        from pytest_resumable_stepmetrics import steplog_record

        @steplog_record(stamp=("attempt",))
        @dataclass
        class Event:
            name: str
            attempt: int = 1

        def test_uses_steplog(steplog):
            with steplog("setup"):
                pass
            steplog.record(Event(name="hello"))
            with steplog("teardown"):
                pass
        """
    )
    result = pytester.runpytest("--steplog-json", "-p", "steplog")
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["*steplog summary:*"])

    json_files = list(pytester.path.glob(".steplog/*.json"))
    assert json_files, "expected a report.json to be written"
    text = json_files[0].read_text(encoding="utf-8")
    assert '"event"' in text
    assert '"steps"' in text


def test_resumable_skips_on_rerun_within_test(pytester):
    pytester.makepyfile(
        """
        def test_resume(steplog):
            ran = []

            def attempt(n):
                steplog.reset_attempt()
                with steplog.resumable("prep") as step:
                    if not step.resumed:
                        ran.append(n)
                with steplog("work") as step:
                    if n == 1:
                        raise RuntimeError("fail once")

            try:
                attempt(1)
            except RuntimeError:
                attempt(2)

            assert ran == [1]
            assert steplog.collector.run.retry_count == 1
        """
    )
    result = pytester.runpytest("-p", "steplog")
    result.assert_outcomes(passed=1)
