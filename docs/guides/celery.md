# Celery Support

django-query-doctor can analyze database queries inside Celery tasks. Since Celery tasks run outside the HTTP request/response cycle, the middleware is not active. Instead, use the `@diagnose_task` decorator or the `diagnose_queries()` context manager.

---

## Installation

Celery support has no extra dependencies -- the decorator works on any callable. The optional extras group exists for version pinning:

```bash
pip install "django-query-doctor[celery]"
```

---

## Why the Middleware Does Not Work

The `QueryDoctorMiddleware` hooks into Django's request/response cycle. Celery tasks do not go through this cycle -- they are executed by Celery workers in a separate process. Therefore:

- The middleware is never invoked for Celery tasks.
- You must explicitly opt in to query analysis per task.

---

## Using the Decorator

Apply `@diagnose_task` beneath the task decorator, and pass an `on_report` callback to receive the results:

```python title="myapp/tasks.py"
import logging

from celery import shared_task
from query_doctor.celery_integration import diagnose_task

logger = logging.getLogger(__name__)


def log_findings(report):
    if report.prescriptions:
        logger.warning("Query issues in task: %d found", report.issues)
        for rx in report.prescriptions:
            logger.warning("  %s: %s", rx.severity.value, rx.description)


@shared_task
@diagnose_task(on_report=log_findings)
def generate_report(report_id):
    """Generate a PDF report for the given report."""
    report = Report.objects.select_related("author").get(pk=report_id)
    entries = ReportEntry.objects.filter(report=report)
    for entry in entries:
        process_entry(entry)
    return f"Report {report_id} generated"
```

The decorator wraps the task execution in a query interceptor, runs every enabled analyzer when the task completes (including when it raises), and passes the populated `DiagnosisReport` to `on_report`.

> **Important:** `@diagnose_task` does not print or log anything by itself, and it does not dispatch to the `REPORTERS` setting. Without an `on_report` callback the analysis results are discarded -- always pass a callback (or use the context manager below) if you want to see the findings.

The bare form also works when you only want capture wired in for a callback added later:

```python
@shared_task
@diagnose_task
def cleanup_task():
    ...
```

If Celery is not installed, `@diagnose_task` still works -- it wraps any plain callable.

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
            location = (
                f"{rx.callsite.filepath}:{rx.callsite.line_number}" if rx.callsite else "?"
            )
            logger.warning("  %s: %s (%s)", rx.severity.value, rx.description, location)
```

This is useful when a task has multiple phases and you only want to analyze the database-intensive portion.

---

## Example: Shipping Findings to Monitoring

The `on_report` callback is the integration point for metrics and alerting:

```python
def on_diagnosis_complete(report):
    if report.prescriptions:
        metrics.increment("query_doctor.issues", len(report.prescriptions))


@shared_task
@diagnose_task(on_report=on_diagnosis_complete)
def process_orders(order_ids):
    orders = Order.objects.filter(pk__in=order_ids).select_related("customer")
    for order in orders:
        fulfill(order)
```

To persist results, render the report yourself inside the callback, e.g. with `query_doctor.reporters.json_reporter.JSONReporter(output_path=...).report(report)`.

---

## Configuration

Celery tasks use the same `QUERY_DOCTOR` settings as the rest of your project (analyzer toggles, thresholds). There are no per-task setting overrides; the decorator's only option is `on_report`.

---

## Further Reading

- [Middleware](middleware.md) -- HTTP request analysis (does not apply to Celery).
- [How It Works](how-it-works.md) -- The four-stage pipeline.
- [Async Support](async-support.md) -- Using with async Django views and ASGI.
