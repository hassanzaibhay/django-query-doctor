# Celery Support

django-query-doctor can analyze database queries inside Celery tasks. Since Celery tasks run outside the HTTP request/response cycle, the middleware is not active. Instead, use the `@diagnose` decorator or the `diagnose_queries()` context manager.

---

## Installation

Install django-query-doctor with the `celery` extras to pull in the Celery integration utilities:

```bash
pip install "django-query-doctor[celery]"
```

This does not add Celery as a dependency -- it enables the Celery-aware task base class and signal hooks.

---

## Why the Middleware Does Not Work

The `QueryDoctorMiddleware` hooks into Django's request/response cycle. Celery tasks do not go through this cycle -- they are executed by Celery workers in a separate process. Therefore:

- The middleware is never invoked for Celery tasks.
- You must explicitly opt in to query analysis per task.

---

## Using the Decorator

The simplest approach is to apply the `@diagnose` decorator to your task function:

```python title="myapp/tasks.py"
from celery import shared_task
from query_doctor.decorators import diagnose


@shared_task
@diagnose
def generate_report(report_id):
    """Generate a PDF report for the given report."""
    report = Report.objects.select_related("author").get(pk=report_id)
    entries = ReportEntry.objects.filter(report=report)
    for entry in entries:
        process_entry(entry)
    return f"Report {report_id} generated"
```

The decorator wraps the task execution in a query interceptor. When the task completes, any prescriptions are logged via the configured reporters.

### Decorator Options

You can pass options to control the analysis:

```python
@shared_task
@diagnose(severity="WARNING", analyzers=["nplusone", "duplicate"])
def send_notifications(user_ids):
    """Send email notifications. Only check for N+1 and duplicates."""
    users = User.objects.filter(pk__in=user_ids)
    for user in users:
        send_email(user.email, build_message(user))
```

---

## Using the Context Manager

For finer control, use `diagnose_queries()` to wrap specific sections of a task:

```python title="myapp/tasks.py"
from celery import shared_task
from query_doctor.context_managers import diagnose_queries


@shared_task
def sync_inventory(warehouse_id):
    """Sync inventory data from external API."""
    warehouse = Warehouse.objects.get(pk=warehouse_id)

    # Only analyze the database-heavy section
    with diagnose_queries() as report:
        products = Product.objects.filter(warehouse=warehouse)
        for product in products:
            update_stock(product)

    if report.prescriptions:
        logger.warning(
            "Query issues in sync_inventory: %d issues found",
            len(report.prescriptions),
        )
        for rx in report.prescriptions:
            logger.warning("  %s: %s (%s)", rx.severity, rx.issue, rx.location)
```

This is useful when a task has multiple phases and you only want to analyze the database-intensive portion.

---

## Accessing Results

Both the decorator and context manager produce a report object. With the context manager, you get it directly via the `as` clause. With the decorator, prescriptions are sent to the configured reporters (console, JSON, log).

To programmatically access results with the decorator, use the callback option:

```python
def on_diagnosis_complete(report):
    if report.prescriptions:
        # Send to monitoring, log, or store in DB
        metrics.increment("query_doctor.issues", len(report.prescriptions))


@shared_task
@diagnose(callback=on_diagnosis_complete)
def process_orders(order_ids):
    orders = Order.objects.filter(pk__in=order_ids).select_related("customer")
    for order in orders:
        fulfill(order)
```

---

## Configuration

Celery tasks use the same `QUERY_DOCTOR` settings as the rest of your project. You can override settings per-task via decorator or context manager arguments:

```python
@shared_task
@diagnose(
    severity="CRITICAL",
    analyzers=["nplusone"],
    reporters=["log"],
)
def heavy_task():
    ...
```

---

## Example: Periodic Task Monitoring

Combine django-query-doctor with Celery Beat to periodically audit a critical task:

```python title="myapp/tasks.py"
from celery import shared_task
from query_doctor.decorators import diagnose


@shared_task
@diagnose(reporters=["json"], output="/var/log/query-doctor/nightly-sync.json")
def nightly_sync():
    """Nightly data synchronization. Query analysis is logged to JSON."""
    ...
```

```python title="settings.py"
CELERY_BEAT_SCHEDULE = {
    "nightly-sync": {
        "task": "myapp.tasks.nightly_sync",
        "schedule": crontab(hour=2, minute=0),
    },
}
```

The JSON report is written after each run, allowing you to track query patterns over time.

---

## Further Reading

- [Middleware](middleware.md) -- HTTP request analysis (does not apply to Celery).
- [How It Works](how-it-works.md) -- The four-stage pipeline.
- [Async Support](async-support.md) -- Using with async Django views and ASGI.
