# Reporters

Reporters format analysis results for different audiences and workflows. Each reporter receives the same list of `Prescription` objects and outputs them in its own format. Multiple reporters can be active simultaneously.

---

## Configuring Reporters

```python title="settings.py"
QUERY_DOCTOR = {
    "REPORTERS": ["console"],  # Default
}
```

All reporters respect `MIN_SEVERITY` to filter output:

```python
QUERY_DOCTOR = {
    "MIN_SEVERITY": "WARNING",  # Only WARNING and CRITICAL
}
```

---

## Console (Rich)

Terminal output with colors and tables when [Rich](https://github.com/Textualize/rich) is installed. Falls back to plain text without it.

```bash
pip install django-query-doctor[rich]
```

```python title="settings.py"
QUERY_DOCTOR = {
    "REPORTERS": ["query_doctor.reporters.ConsoleReporter"],
    "CONSOLE_COLOR_SCHEME": "auto",     # "auto", "dark", "light", "none"
    "CONSOLE_VERBOSITY": "normal",      # "quiet", "normal", "verbose"
    "CONSOLE_SHOW_SQL": True,
    "CONSOLE_MAX_SQL_LENGTH": 200,
}
```

Example output (plain text fallback):

```
[query-doctor] GET /api/books/ (127 queries, 4 prescriptions)

[CRITICAL] N+1 Query
  50 queries fetching Author for each Book.
  Location: views.py:42
  Fix: Add select_related('author') to queryset

[WARNING] Duplicate Query
  Query executed 12 times: SELECT "books_category"."id" ...
  Location: serializers.py:18
  Fix: Hoist query above the loop
```

Verbosity levels: `"quiet"` shows only CRITICAL/WARNING. `"verbose"` adds full SQL and stack traces. Set `CONSOLE_COLOR_SCHEME: "none"` or `NO_COLOR=1` to disable colors.

---

## JSON

Structured `.json` files for CI/CD pipelines and automated tooling.

```python title="settings.py"
QUERY_DOCTOR = {
    "REPORTERS": ["query_doctor.reporters.JSONReporter"],
    "JSON_OUTPUT_DIR": "reports/query-doctor/",
    "JSON_INDENT": 2,
    "JSON_INCLUDE_SQL": True,
}
```

Example output:

```json
{
  "version": "1.0.0",
  "request": {
    "method": "GET",
    "path": "/api/books/",
    "total_queries": 127,
    "total_time_ms": 342.5
  },
  "summary": {
    "total_prescriptions": 4,
    "by_severity": {"critical": 1, "warning": 2, "info": 1}
  },
  "prescriptions": [
    {
      "severity": "critical",
      "analyzer": "NPlusOneAnalyzer",
      "issue": "50 queries fetching Author for each Book",
      "location": {"file": "myapp/views.py", "line": 42},
      "suggestion": "Add select_related('author') to queryset"
    }
  ]
}
```

Filter with jq: `cat reports/*.json | jq '.prescriptions[] | select(.severity == "critical")'`

---

## HTML Dashboard

Standalone, self-contained HTML file with sortable tables, severity filters, and expandable SQL sections.

```python title="settings.py"
QUERY_DOCTOR = {
    "REPORTERS": ["query_doctor.reporters.HTMLReporter"],
    "HTML_OUTPUT_DIR": "reports/html/",
    "HTML_TITLE": "Query Doctor Report",
    "HTML_MAX_REPORTS": 50,
}
```

Generate via command:

```bash
python manage.py diagnose_project --format html --output reports/project-health.html
```

Features: summary dashboard with severity counts, sortable prescription table (by severity, analyzer, location, query count), expandable SQL sections, inline CSS/JS with no external dependencies.

---

## Log File

Outputs prescriptions through Python's `logging` module, integrating with your existing log infrastructure (files, Sentry, ELK, CloudWatch).

```python title="settings.py"
QUERY_DOCTOR = {
    "REPORTERS": ["query_doctor.reporters.LogReporter"],
    "LOG_LOGGER_NAME": "query_doctor",
    "LOG_LEVEL": "WARNING",
    "LOG_INCLUDE_SQL": False,
}
```

Severity mapping: CRITICAL → `logging.ERROR`, WARNING → `logging.WARNING`, INFO → `logging.INFO`.

```python title="settings.py"
LOGGING = {
    "version": 1,
    "handlers": {
        "query_doctor_file": {
            "level": "WARNING",
            "class": "logging.FileHandler",
            "filename": "logs/query_doctor.log",
        },
    },
    "loggers": {
        "query_doctor": {
            "handlers": ["query_doctor_file"],
            "level": "WARNING",
        },
    },
}
```

---

## OpenTelemetry

Exports prescriptions as OTel span attributes and events into your observability stack (Jaeger, Datadog, New Relic, Honeycomb).

```bash
pip install django-query-doctor[otel]
```

```python title="settings.py"
QUERY_DOCTOR = {
    "REPORTERS": ["query_doctor.reporters.OpenTelemetryReporter"],
    "OTEL_SERVICE_NAME": "my-django-app",
    "OTEL_ENDPOINT": "http://localhost:4317",
    "OTEL_INCLUDE_SQL": False,  # Disable in production to avoid leaking data
}
```

Span attributes added to the current request span:

```
query_doctor.total_queries = 127
query_doctor.total_prescriptions = 4
query_doctor.critical_count = 1
```

Each prescription is emitted as a span event with structured attributes (severity, analyzer, issue, location, suggestion).

Place `QueryDoctorMiddleware` **after** the OTel middleware so it can attach to the existing request span.

---

## Next Steps

- [Configuration](../getting-started/configuration.md) — all reporter settings
- [CI/CD Integration](../guides/ci-integration.md) — using JSON reporter in pipelines
- [Benchmark Dashboard](../guides/benchmark-dashboard.md) — QueryTurbo-specific HTML report
