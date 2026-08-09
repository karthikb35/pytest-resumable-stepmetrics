# pytest-resumable-stepmetrics

> **When a test retries, you lose the story.**
> Which step failed? Did the welcome email fire twice? Was the workspace ever
> actually provisioned? Your only clue is a wall of logs.

`pytest-resumable-stepmetrics` gives you **structured step-level metadata** inside
every test — with **per-attempt tracking**, **resume-on-retry** for idempotent
steps, and a **JSON report** you can query, store, or push to a dashboard.

```bash
pip install pytest-resumable-stepmetrics
```

---

## What you get

A SaaS onboarding flow fails during workspace provisioning and retries.
Your terminal shows this **automatically** — no extra code:

```
steplog summary:
====================================== = ======================================
  Test:    test_user_onboarding.py::test_new_user_signup
  Status:  PASSED
  Retries: 1

 Steps:
+---+---------------------+---------+---------+-------------+--------+----------+------+
| # | Step                | Attempt | Status  | Duration(s) | Errors | Warnings | Info |
+===+=====================+=========+=========+=============+========+==========+======+
| 1 | create account      | 1       | passed  | 0.065       | 0      | 0        | 0    |
| 2 | send welcome email  | 1       | passed  | 0.031       | 0      | 0        | 0    |
| 3 | provision workspace | 1       | failed  | 0.140       | 0      | 0        | 0    |
| 4 | create account      | 2       | passed  | 0.061       | 0      | 0        | 0    |
| 5 | send welcome email  | 2       | skipped | 0.000       | 0      | 0        | 0    |
| 6 | provision workspace | 2       | passed  | 0.141       | 0      | 0        | 0    |
| 7 | assign trial plan   | 2       | passed  | 0.041       | 0      | 0        | 0    |
+---+---------------------+---------+---------+-------------+--------+----------+------+

 provisioning_actions:
+-----------+-------------+--------+-------------+---------+
| Resource  | Action      | Status | Duration Ms | Attempt |
+===========+=============+========+=============+=========+
| user      | created     | ok     | 61.2        | 1       |
| email     | sent        | ok     | 31.7        | 1       |
| workspace | provisioned | error  | 143.8       | 1       |
| user      | created     | ok     | 61.2        | 2       |
| workspace | provisioned | ok     | 143.8       | 2       |
| plan      | assigned    | ok     | 38.4        | 2       |
+-----------+-------------+--------+-------------+---------+
```

**Row 3:** `provision workspace` failed on attempt 1 — exact failure point, no log digging.
**Row 5:** `send welcome email` is `skipped` on attempt 2 — it already fired; no duplicate email sent.
**`provisioning_actions`:** every backend event across both attempts, with attempt numbers — full audit trail.

---

## Quick start

```python
def test_flow(steplog):
    with steplog("step one"):
        ...
    with steplog("step two"):
        ...
```

```bash
pytest --steplog-json    # also writes .steplog/report.json per test
```

---

## End-to-end example

> Fully runnable with no extra dependencies:
> [`examples/test_user_onboarding.py`](examples/test_user_onboarding.py)

### Domain model

```python
from dataclasses import dataclass
from pytest_resumable_stepmetrics import steplog_record

@steplog_record(key="provisioning_actions", stamp=("attempt",))
@dataclass
class ProvisioningAction:
    resource: str    # "user" | "workspace" | "email" | "plan"
    action: str      # "created" | "provisioned" | "sent" | "assigned"
    status: str      # "ok" | "error"
    duration_ms: float
    attempt: int = 1   # filled automatically from the steplog context
```

Registering with `@steplog_record` means:
- `provisioning_actions` appears as its own array in `report.json`
- a terminal table is rendered after each test — zero extra code
- `attempt` is stamped automatically — no manual wiring

### The test

```python
def test_new_user_signup(steplog):
    svc = OnboardingService()
    user_id = None

    def run():
        nonlocal user_id
        steplog.reset_attempt()   # first line of every attempt

        # Stateful — re-runs each attempt (account must exist before workspace)
        with steplog("create account"):
            result = svc.create_account(email="alice@example.com")
            user_id = result["user_id"]
            steplog.record(ProvisioningAction("user", "created", "ok", 61.2))

        # Idempotent — skip on retry so Alice doesn't get two welcome emails
        def send_email():
            svc.send_welcome_email(user_id=user_id)
            steplog.record(ProvisioningAction("email", "sent", "ok", 31.7))

        steplog.run("send welcome email", send_email)

        # Stateful — re-runs each attempt
        with steplog("provision workspace"):
            result = svc.provision_workspace(user_id=user_id)
            steplog.record(ProvisioningAction("workspace", "provisioned", "ok", 143.8))

        with steplog("assign trial plan"):
            svc.assign_trial_plan(user_id=user_id, workspace_id=result["workspace_id"])
            steplog.record(ProvisioningAction("plan", "assigned", "ok", 38.4))

    # Retry loop — works with tenacity / pytest-rerunfailures / anything
    for attempt in range(2):
        try:
            run()
            return
        except Exception:
            if attempt == 1:
                raise
```

### Sample `report.json`

```json
{
  "run": {
    "test_nodeid": "test_user_onboarding.py::test_new_user_signup",
    "status": "passed",
    "started_at": "2026-08-09T08:25:39.092605+00:00",
    "ended_at": "2026-08-09T08:25:41.340120+00:00",
    "duration_seconds": 2.248,
    "retry_count": 1,
    "info": {}
  },
  "steps": [
    {
      "name": "create account",
      "attempt": 1,
      "resumed": false,
      "status": "passed",
      "duration_seconds": 0.065,
      "error": null
    },
    {
      "name": "send welcome email",
      "attempt": 1,
      "resumed": false,
      "status": "passed",
      "duration_seconds": 0.031,
      "error": null
    },
    {
      "name": "provision workspace",
      "attempt": 1,
      "resumed": false,
      "status": "failed",
      "duration_seconds": 0.140,
      "error": "workspace provisioner timed out after 30s"
    },
    {
      "name": "create account",
      "attempt": 2,
      "resumed": false,
      "status": "passed",
      "duration_seconds": 0.061,
      "error": null
    },
    {
      "name": "send welcome email",
      "attempt": 2,
      "resumed": true,
      "status": "skipped",
      "duration_seconds": 0.0,
      "error": null
    },
    {
      "name": "provision workspace",
      "attempt": 2,
      "resumed": false,
      "status": "passed",
      "duration_seconds": 0.141,
      "error": null
    },
    {
      "name": "assign trial plan",
      "attempt": 2,
      "resumed": false,
      "status": "passed",
      "duration_seconds": 0.041,
      "error": null
    }
  ],
  "provisioning_actions": [
    { "resource": "user",      "action": "created",     "status": "ok",    "duration_ms": 61.2,  "attempt": 1 },
    { "resource": "email",     "action": "sent",        "status": "ok",    "duration_ms": 31.7,  "attempt": 1 },
    { "resource": "workspace", "action": "provisioned", "status": "error", "duration_ms": 143.8, "attempt": 1 },
    { "resource": "user",      "action": "created",     "status": "ok",    "duration_ms": 61.2,  "attempt": 2 },
    { "resource": "workspace", "action": "provisioned", "status": "ok",    "duration_ms": 143.8, "attempt": 2 },
    { "resource": "plan",      "action": "assigned",    "status": "ok",    "duration_ms": 38.4,  "attempt": 2 }
  ]
}
```

---

## Retry & attempt tracking

Call `steplog.reset_attempt()` as the first line of each attempt.
`run.retry_count` and each step's `attempt` field are tracked automatically.
The **Attempt** column appears in the terminal table only when retries occur.

Works with any retry mechanism — `tenacity`, `pytest-rerunfailures`, a manual
loop, whatever you already use.

---

## Resume-on-retry

Two forms — pick the one that fits your code style.

### Callable (guard-free) — recommended

```python
steplog.run("send welcome email", send_email)
# send_email is simply not called on retry — no guard needed
```

### Context manager (with guard)

```python
with steplog.resumable("send welcome email") as step:
    if not step.resumed:   # guard required — with-blocks always execute their body
        send_email()
```

> ⚠️ Use resume only for **pure / idempotent** work — token fetch, email send,
> file download, name resolution. Stateful steps (account creation, DB writes,
> workspace provisioning) must re-run — use plain `steplog("name")`.

---

## Custom records

`steplog.record(obj)` accepts any dataclass. Register with `@steplog_record`
to control the JSON key, auto-stamped fields, and an optional custom renderer:

```python
@steplog_record(key="db_queries", stamp=("attempt",))
@dataclass
class DbQuery:
    table: str
    operation: str
    rows_affected: int
    duration_ms: float
    attempt: int = 1
```

An unregistered dataclass also works — it uses its snake_case class name as the
key and auto-tabulates all fields. No extra wiring needed.

---

## The `steplog` fixture API

| Call | What it does |
|---|---|
| `steplog("name")` | Track a step — context manager, body always runs. |
| `steplog.resumable("name")` | Track a resumable step — use `if not step.resumed:` guard. |
| `steplog.run("name", func, *a, **kw)` | Track a callable step — `func` is not called on retry (guard-free). |
| `steplog.record(obj)` | Attach a custom dataclass record to the current attempt. |
| `steplog.reset_attempt()` | Advance the attempt counter — call first in each retry. |
| `steplog.context` | Mutable dict auto-stamped onto records (`attempt`, custom fields). |
| `steplog.collector` | The underlying `StepLogCollector` for advanced use. |

---

## JSON report

```bash
pytest --steplog-json                  # writes .steplog/<test-id>/report.json
pytest --steplog-json-dir=reports/     # custom output directory
```

Each file contains `run`, `steps`, and one array per registered record type.
Ingest into Elasticsearch, a database, or a CI dashboard — the schema is stable.

---

## License

MIT
