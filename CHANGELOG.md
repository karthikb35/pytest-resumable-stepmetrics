# Changelog

All notable changes to this project are documented here. This project adheres
to [Semantic Versioning](https://semver.org/).

## [0.1.0] - Unreleased

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
