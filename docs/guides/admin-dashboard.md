# Admin Dashboard

django-query-doctor includes a lightweight, staff-only dashboard view that shows recent query diagnosis reports. It keeps the last 50 reports in an in-memory ring buffer -- no database tables, no migrations.

---

## Setup

Three steps. First, make sure the middleware is active (it is what records reports):

```python title="settings.py"
MIDDLEWARE = [
    ...,
    "query_doctor.middleware.QueryDoctorMiddleware",
]
```

Second, enable dashboard recording (it is **off** by default):

```python title="settings.py"
QUERY_DOCTOR = {
    "ADMIN_DASHBOARD": {"enabled": True},
}
```

Third, mount the dashboard URLs in your project urlconf:

```python title="urls.py"
from django.urls import include, path

urlpatterns = [
    ...,
    path("admin/query-doctor/", include("query_doctor.urls")),
]
```

The dashboard is then available at `/admin/query-doctor/dashboard/`.

---

## What It Shows

For each analyzed request (newest first):

- Timestamp, URL path, and HTTP method.
- Total queries and total query time.
- Issue count, with a critical flag when any CRITICAL finding is present.
- Expandable prescription details: issue type, severity, description, fix suggestion, and `file:line` callsite.

Plus summary counters across the buffer: total reports, total issues, and the number of requests with critical findings.

---

## Storage Model

Reports live in a **process-local, in-memory ring buffer** capped at 50 entries. Consequences:

- Nothing is written to your database; there are no `query_doctor` models or migrations.
- The buffer is empty after every server restart.
- With multiple worker processes, each worker has its own buffer; the dashboard shows the buffer of whichever worker serves the page.

This makes the dashboard a development convenience, not a monitoring system. For durable history, write JSON reports (`JSON_REPORT_PATH`, or `check_queries --format json --output ...`) and keep them in your own storage.

---

## Permissions

The view requires an authenticated user with `is_staff` (enforced with `login_required` and a staff check). There is no separate dashboard permission.

---

## Configuration Reference

| Setting | Default | Description |
|---|---|---|
| `ADMIN_DASHBOARD.enabled` | `False` | When `True`, the middleware records each analyzed request into the dashboard buffer. |
| `ADMIN_DASHBOARD.max_reports` | `50` | Size of the in-memory ring buffer. Read once, when the buffer is first used, so a change takes effect on process restart. |

---

## Further Reading

- [How It Works](how-it-works.md) -- The analysis pipeline that feeds the dashboard.
- [Middleware](middleware.md) -- The recording entry point.
- [Management Commands](management-commands.md) -- `diagnose_project` for project-wide HTML reports.
