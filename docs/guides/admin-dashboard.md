# Admin Dashboard

django-query-doctor includes a built-in Django admin dashboard that provides a visual overview of query health across your project. No additional packages are required.

---

## Setup

Add `query_doctor` to your `INSTALLED_APPS` (you likely already have this):

```python title="settings.py"
INSTALLED_APPS = [
    ...,
    "django.contrib.admin",
    "query_doctor",
]
```

That is all. The dashboard registers itself in the Django admin automatically. Navigate to `/admin/` and you will see a "Query Doctor" section.

---

## Features

### Overview Page

The main dashboard page shows:

- **Total queries analyzed** across all tracked requests.
- **Total issues found**, broken down by severity (CRITICAL, WARNING, INFO).
- **Overall health score** from 0 to 100, based on the ratio of clean requests to flagged ones.
- **Average queries per request** with a trend indicator.

### Top Issues

A ranked list of the most impactful query issues across your project:

| Rank | Issue | Endpoint | Occurrences | Est. Savings |
|------|-------|----------|-------------|--------------|
| 1 | N+1 on `myapp_author` | `/api/books/` | 342 | ~1.2s/req |
| 2 | Duplicate query | `/dashboard/` | 89 | ~0.4s/req |
| 3 | Missing index on `published_date` | `/api/books/` | 67 | ~0.3s/req |

Each row links to a detail page with the full prescription, including the exact file:line and fix code.

### Endpoint Health

A per-endpoint view showing:

- Total queries per request (average, min, max).
- Number of active prescriptions.
- Health status: green (no issues), yellow (INFO/WARNING), red (CRITICAL).
- Historical query count chart (requires periodic scanning).

### Trend Tracking

When you run `diagnose_project` periodically (e.g., nightly via a cron job or Celery Beat), the dashboard tracks query health over time:

- Query count trends per endpoint.
- New issues introduced vs. issues resolved.
- Health score history.

> **Tip:** Set up a scheduled task to run `diagnose_project` nightly and save the results to a file. This helps you track whether your codebase is getting better or worse over time.
>
> ```bash
> # Cron example: run every night at 2 AM
> 0 2 * * * cd /path/to/project && python manage.py diagnose_project --format json --output reports/nightly.json
> ```

---

## Dashboard Data Storage

The dashboard stores analysis results in Django's database using its own models. Run migrations to create the necessary tables:

```bash
python manage.py migrate query_doctor
```

Data is stored only when the middleware is active. The dashboard does not add any database overhead to your application's normal operation.

### Data Retention

By default, the dashboard retains data for 30 days. Configure the retention period in your settings:

```python title="settings.py"
QUERY_DOCTOR = {
    "DASHBOARD_RETENTION_DAYS": 90,  # Keep 90 days of history
}
```

---

## Permissions

The dashboard is accessible to users with the `is_staff` flag, same as the rest of the Django admin. You can further restrict access by assigning the `query_doctor.view_dashboard` permission:

```python
from django.contrib.auth.models import Permission

# Grant dashboard access to a specific user
permission = Permission.objects.get(codename="view_dashboard")
user.user_permissions.add(permission)
```

---

## Customization

### Disabling the Dashboard

If you use django-query-doctor but do not want the admin integration:

```python title="settings.py"
QUERY_DOCTOR = {
    "ADMIN_DASHBOARD": False,
}
```

### Custom Admin Site

If you use a custom `AdminSite`, the dashboard auto-discovers it. If it does not appear, register it manually:

```python title="myapp/admin.py"
from query_doctor.admin import QueryDoctorDashboard

custom_admin_site.register_dashboard(QueryDoctorDashboard)
```

---

## Further Reading

- [How It Works](how-it-works.md) -- The analysis pipeline that feeds the dashboard.
- [Management Commands](management-commands.md) -- Using `diagnose_project` to analyze your codebase.
- [CI Integration](ci-integration.md) -- Automated scanning for the dashboard.
