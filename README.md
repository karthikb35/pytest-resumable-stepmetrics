# pytest-resumable-stepmetrics

Structured **step-level metadata**, **retry / attempt tracking**, and
**resume-on-retry** for pytest — plus a tiny **extension system** so you can
attach your own domain records (and get JSON + terminal reporting for free).

```bash
pip install pytest-resumable-stepmetrics
```

## Why

- Track named **steps** inside a test with status, duration and captured logs.
- Know **which attempt** a step (or record) belongs to when a test retries.
- **Resume** past already-succeeded, idempotent steps on a retry — skip the
  expensive work instead of re-running everything from the top.
- Attach **your own structured records** (a dataclass) and have them serialised
  to `report.json` and rendered as a terminal table automatically.

## Quick start

```python
def test_flow(steplog):
    with steplog("setup"):
        ...
    with steplog("do work"):
        ...
```

Run with a JSON report:

```bash
pytest --steplog-json
```

## Retry & attempt tracking

Call `steplog.reset_attempt()` as the first statement of each attempt (e.g.
inside a retry loop). `run.retry_count` and each step's `attempt` are tracked
automatically:

```python
from retry import retry  # any retry mechanism works

def test_with_retries(steplog):
    @retry(tries=3, delay=0)
    def run():
        steplog.reset_attempt()          # first line of every attempt
        with steplog("environment"):
            ...
        with steplog("flash"):
            ...                          # raise to trigger a retry
    run()
```

The steps table gains an **Attempt** column automatically when retries occur.

## Resume-on-retry (opt-in, idempotent steps only)

`steplog.resumable("name")` records success and, on a later attempt, **skips the
body** if it already passed. Guard the body with `step.resumed`:

```python
with steplog.resumable("download artifact") as step:
    if not step.resumed:
        download()          # runs once; skipped on later attempts
```

> ⚠️ Only use `resumable` for **pure / idempotent** steps whose effects survive a
> retry (downloads, name resolution, hashing). Stateful steps (deploys, power
> cycles, connection setup) should use plain `steplog(...)` so they re-run.

### Guard-free resume with `steplog.run(...)`

A `with` block **always** runs its body — so `resumable` needs the
`if not step.resumed:` guard. If you'd rather skip the work automatically with
no guard, pass the work as a callable to `steplog.run(...)`; it simply isn't
called when the step already passed:

```python
def download():
    ...expensive work...

def test_flow(steplog):
    steplog.reset_attempt()
    steplog.run("download artifact", download)   # skipped entirely on retry
```

`steplog.run` returns whatever the callable returns (or `None` when skipped) and
forwards any extra `*args` / `**kwargs` to it.

## Custom records (the extension point)

Attach any dataclass with `steplog.record(...)`. Register it with
`@steplog_record` to name its report section and auto-stamp fields (like
`attempt`) from the live context:

```python
from dataclasses import dataclass
from pytest_resumable_stepmetrics import steplog_record

@steplog_record(key="deploy_actions", stamp=("attempt",))
@dataclass
class DeployAction:
    component: str
    action: str
    attempt: int = 1        # auto-filled from the current attempt

def test_deploy(steplog):
    steplog.reset_attempt()
    steplog.record(DeployAction(component="api", action="deployed"))
```

This produces a `deploy_actions` array in `report.json` **and** a terminal
table — no extra wiring. A plain (unregistered) dataclass also works; it uses
the snake_case class name as its key and auto-tabulates its fields.

Provide a custom renderer for full control:

```python
@steplog_record(key="samples", render=lambda rows: my_table(rows))
@dataclass
class BenchSample:
    metric: str
    value: float
```

## The `steplog` API

| Call | Purpose |
|---|---|
| `steplog("name")` | Track a step (context manager). |
| `steplog.resumable("name")` | Track a step that skips on retry once passed (guard with `step.resumed`). |
| `steplog.run("name", func, *a, **kw)` | Track a callable step; skips *calling* `func` on retry (guard-free). |
| `steplog.record(obj)` | Attach a custom dataclass record. |
| `steplog.reset_attempt()` | Advance the attempt counter (call first each attempt). |
| `steplog.context` | Mutable dict used to auto-stamp records. |
| `steplog.collector` | The underlying `StepLogCollector`. |

## End-to-end example (API testing)

### The test

```python
# tests/test_create_order_flow.py
import pytest
from dataclasses import dataclass
from pytest_resumable_stepmetrics import steplog_record


@steplog_record(key="api_requests", stamp=("attempt",))
@dataclass
class ApiRequest:
    """One HTTP call made during the test — auto-stamped with the current attempt."""
    endpoint: str
    method: str
    status_code: int
    latency_ms: float
    attempt: int = 1          # filled automatically from steplog context


def test_create_order_flow(steplog):
    """Create an order via a REST API.  Retries once if the first attempt fails."""

    def run():
        steplog.reset_attempt()   # must be the first call in every attempt

        # --- authenticate once; skip on retry if it already passed ---
        steplog.run("authenticate", authenticate)

        # --- GET /products ---
        with steplog("GET /products"):
            resp = get_products()
            steplog.record(ApiRequest("/api/products", "GET", resp.status_code, resp.elapsed_ms))
            assert resp.status_code == 200

        # --- POST /orders ---
        with steplog("POST /orders"):
            resp = create_order(product_id=resp.json()[0]["id"])
            steplog.record(ApiRequest("/api/orders", "POST", resp.status_code, resp.elapsed_ms))
            assert resp.status_code == 201
            assert "id" in resp.json(), "order id missing from response"

    retry(run, tries=2)
```

### Sample JSON report (`report.json`)

Generated by `pytest --steplog-json`. One file per test under `.steplog/`.

```json
{
  "run": {
    "test_nodeid": "tests/test_create_order_flow.py::test_create_order_flow",
    "status": "passed",
    "started_at": "2026-08-09T08:25:39.092605+00:00",
    "ended_at": "2026-08-09T08:25:41.340120+00:00",
    "duration_seconds": 2.248,
    "retry_count": 1,
    "info": {}
  },
  "steps": [
    {
      "name": "authenticate",
      "attempt": 1,
      "resumed": false,
      "status": "passed",
      "started_at": "2026-08-09T08:25:39.092605+00:00",
      "ended_at": "2026-08-09T08:25:39.512100+00:00",
      "duration_seconds": 0.419,
      "error": null,
      "info": {}
    },
    {
      "name": "GET /products",
      "attempt": 1,
      "resumed": false,
      "status": "passed",
      "started_at": "2026-08-09T08:25:39.512100+00:00",
      "ended_at": "2026-08-09T08:25:39.654400+00:00",
      "duration_seconds": 0.142,
      "error": null,
      "info": {}
    },
    {
      "name": "POST /orders",
      "attempt": 1,
      "resumed": false,
      "status": "failed",
      "started_at": "2026-08-09T08:25:39.654400+00:00",
      "ended_at": "2026-08-09T08:25:39.942000+00:00",
      "duration_seconds": 0.288,
      "error": "order id missing from response",
      "info": {}
    },
    {
      "name": "authenticate",
      "attempt": 2,
      "resumed": true,
      "status": "skipped",
      "started_at": "2026-08-09T08:25:39.942000+00:00",
      "ended_at": "2026-08-09T08:25:39.942000+00:00",
      "duration_seconds": 0.0,
      "error": null,
      "info": { "resumed": true }
    },
    {
      "name": "GET /products",
      "attempt": 2,
      "resumed": false,
      "status": "passed",
      "started_at": "2026-08-09T08:25:39.942000+00:00",
      "ended_at": "2026-08-09T08:25:40.084300+00:00",
      "duration_seconds": 0.142,
      "error": null,
      "info": {}
    },
    {
      "name": "POST /orders",
      "attempt": 2,
      "resumed": false,
      "status": "passed",
      "started_at": "2026-08-09T08:25:40.084300+00:00",
      "ended_at": "2026-08-09T08:25:40.371400+00:00",
      "duration_seconds": 0.287,
      "error": null,
      "info": {}
    }
  ],
  "api_requests": [
    { "endpoint": "/api/products", "method": "GET",  "status_code": 200, "latency_ms": 142.3, "attempt": 1 },
    { "endpoint": "/api/orders",   "method": "POST", "status_code": 201, "latency_ms": 287.1, "attempt": 1 },
    { "endpoint": "/api/products", "method": "GET",  "status_code": 200, "latency_ms": 142.3, "attempt": 2 },
    { "endpoint": "/api/orders",   "method": "POST", "status_code": 201, "latency_ms": 287.1, "attempt": 2 }
  ]
}
```

What the fields tell you:
- `retry_count: 1` — the test needed one retry.
- `authenticate` at attempt 2 has `"resumed": true`, `"status": "skipped"` — it was guard-free skipped by `steplog.run`.
- `POST /orders` at attempt 1 shows `"status": "failed"` with the assertion message — exact failure point, no digging through logs.
- `api_requests` contains every HTTP call across all attempts with its attempt number — full per-attempt audit trail.

## JSON report

`--steplog-json` writes one `report.json` per test under `.steplog/`
(override with `--steplog-json-dir`). It contains `run`, `steps`, and one array
per registered record type.

## License

MIT
