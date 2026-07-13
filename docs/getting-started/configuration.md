# Configuration

django-query-doctor works with zero configuration. Every setting has a sensible default (see `query_doctor.conf.DEFAULT_CONFIG`). Override only what you need.

## All Settings

Add these to your Django `settings.py`. This example shows every setting that's actually read by the code — verified against `conf.py` and each key's call site, not assumed:

```python title="settings.py"
QUERY_DOCTOR = {
    # Master on/off switch for the middleware
    "ENABLED": True,

    # Fraction of requests to instrument (1.0 = every request)
    "SAMPLE_RATE": 1.0,

    # Capture Python stack traces to map queries to file:line.
    # Disabling this is faster but prescriptions lose their callsite.
    "CAPTURE_STACK_TRACES": True,

    # Per-analyzer config. Keys are short names, not dotted class paths.
    # Analyzers not listed here use their own defaults (all enabled).
    "ANALYZERS": {
        "nplusone": {"enabled": True, "threshold": 3},
        "duplicate": {"enabled": True, "threshold": 2},
        "missing_index": {"enabled": True},
        "fat_select": {"enabled": True, "threshold": 8},
        "queryset_eval": {"enabled": True},
        "complexity": {"enabled": True, "threshold": 8},
        "serializer_method": {"enabled": True},
    },

    # Reporter names, not class paths: "console", "json", "log".
    "REPORTERS": ["console"],

    # Where the JSON reporter writes output, if "json" is in REPORTERS.
    "JSON_REPORT_PATH": None,

    # URL paths to skip entirely (middleware won't instrument these requests).
    "IGNORE_URLS": ["/admin/", "/static/"],

    # Per-request query budget defaults, used by the @query_budget decorator
    # when it isn't given explicit max_queries/max_time_ms arguments.
    "QUERY_BUDGET": {
        "DEFAULT_MAX_QUERIES": None,
        "DEFAULT_MAX_TIME_MS": None,
    },

    # Admin-integrated dashboard showing recent diagnosis reports.
    "ADMIN_DASHBOARD": {"enabled": False, "max_reports": 50},
}
```

There is no `HTMLReporter` entry for `REPORTERS` — `"console"`, `"json"`, and `"log"` are the only recognized names. HTML output comes from a separate management command (`query_doctor_report`), not the reporter pipeline.

## Environment-Based Toggle

!!! tip "Recommended for production"
    Disable the middleware in production and use management commands in CI instead.

```python title="settings.py"
import os

QUERY_DOCTOR = {
    "ENABLED": os.getenv("QUERY_DOCTOR_ENABLED", "false").lower() == "true",
}
```

There is no `QUERY_DOCTOR_ENABLED` Django setting read by the code — `ENABLED` inside the `QUERY_DOCTOR` dict is what the middleware checks. Reading an environment variable into it, as above, is a pattern you apply yourself.

## Per-Analyzer Configuration

Each analyzer reads its config from `ANALYZERS.<short_name>`. `enabled` is checked by every built-in analyzer (`BaseAnalyzer.is_enabled()`); `threshold` (or a similarly-named key) is analyzer-specific — see the [Analyzers](../analyzers/overview.md) section for what each one supports. Disabling an analyzer here also affects `fix_queries` and `check_queries`, since both discover analyzers the same way.

## Reporter Configuration

Multiple reporters can be active simultaneously — `REPORTERS` is a list, and each recognized name adds its reporter:

```python title="settings.py"
QUERY_DOCTOR = {
    "REPORTERS": ["console", "json"],
    "JSON_REPORT_PATH": "reports/query-doctor.json",
}
```

`console` uses Rich if it's installed (`pip install django-query-doctor[rich]`), falling back to plain text otherwise. `log` sends prescriptions through Python's standard `logging` module instead of stdout.

## Not Yet Wired

`STACK_TRACE_EXCLUDE`, `IGNORE_PATTERNS`, and `QUERYIGNORE_PATH` exist in `DEFAULT_CONFIG` but aren't read by any code path today — setting them has no effect. To suppress known false positives, use a `.queryignore` file at your project root instead (see the [.queryignore guide](../guides/query-ignore.md)); its location isn't configurable via `QUERY_DOCTOR` settings.
