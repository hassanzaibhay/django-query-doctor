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
    # Read by the middleware; other entry points always capture.
    "CAPTURE_STACK_TRACES": True,

    # Extra path fragments to skip when locating the user-code frame,
    # added to the built-in exclusions (query_doctor, Django internals,
    # stdlib). Use this when a wrapper library sits between your code and
    # the ORM and keeps getting blamed for the query.
    "STACK_TRACE_EXCLUDE": [],

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
    # max_reports sizes the in-memory ring buffer, which is built on first
    # use -- changing it after reports have been recorded has no effect
    # until the process restarts.
    "ADMIN_DASHBOARD": {"enabled": False, "max_reports": 50},

    # Path to the .queryignore file itself, when it is not beside manage.py.
    "QUERYIGNORE_PATH": None,

    # Module suffixes check_serializers imports from each app when
    # discovering DRF serializers for static analysis.
    "AST_ANALYSIS": {
        "SERIALIZER_MODULES": [
            "serializers",
            "api.serializers",
            "api.v1.serializers",
            "api.v2.serializers",
        ],
    },
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

## Unrecognized Reporter Names

A name `REPORTERS` doesn't recognize produces no reporter. Since a typo and an unsupported name both simply yield nothing, query_doctor emits a `QueryDoctorWarning` naming the entry and listing the recognized names:

```python title="settings.py"
QUERY_DOCTOR = {"REPORTERS": ["console", "consoel"]}  # QueryDoctorWarning: 'consoel'
```

Suppress the category with `-W ignore::query_doctor.QueryDoctorWarning` if you have a reason to keep an unrecognized entry. Note that suites running `-W error` will fail on it, which is the point — the alternative is a reporter you believe is active and is not.

## Locating `.queryignore`

By default the ignore file is `.queryignore` beside your project root (the directory containing `manage.py`). `QUERYIGNORE_PATH` names the file directly when it lives somewhere else:

```python title="settings.py"
QUERY_DOCTOR = {"QUERYIGNORE_PATH": "/etc/myapp/queryignore.conf"}
```

It must name the **file**, not the directory containing it. A path that doesn't resolve emits a `QueryDoctorWarning` and falls back to project-root discovery — analysis never fails the request, but the ignored setting is reported rather than silently dropped. See the [.queryignore guide](../guides/query-ignore.md) for the rule syntax.
