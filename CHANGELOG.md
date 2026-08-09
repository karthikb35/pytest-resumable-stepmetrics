# Changelog

All notable changes to this project are documented here. This project adheres
to [Semantic Versioning](https://semver.org/).

## [0.1.3] - 2026-08-09

### Changed
- README: switched example to SaaS user onboarding scenario; real terminal output.
- Replaced `examples/test_order_flow.py` with `examples/test_user_onboarding.py`.

## [0.1.2] - 2026-08-09

### Changed
- README fully rewritten: problem hook, real terminal output, runnable example.
- Added `examples/test_order_flow.py` — self-contained runnable example (no extra deps).

## [0.1.1] - 2026-08-09

### Changed
- README: added end-to-end API testing example, `ApiRequest` domain model, and
  annotated sample `report.json`.

## [0.1.0] - 2026-08-09

### Added
- `steplog` fixture with `steplog(name)` step tracking.
- Retry / attempt tracking via `steplog.reset_attempt()` (`run.retry_count`,
  per-step `attempt`).
- `steplog.resumable(name)` — resume-on-retry for idempotent steps.
- `steplog.run(name, func, *args, **kwargs)` — guard-free callable form that
  skips *calling* the function on retry once it has passed.
- Custom-record extension system: `steplog.record(obj)` and the
  `@steplog_record` decorator with `key`, `stamp` and `render` options.
- Terminal summary tables and `--steplog-json` per-test JSON reports.
