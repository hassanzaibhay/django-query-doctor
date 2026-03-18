# Configuration

django-query-doctor works with zero configuration. Every setting has a sensible default. Override only what you need.

## All Settings

Add these to your Django `settings.py`:
```python title="settings.py"
QUERY_DOCTOR = {
    # Master on/off switch
    "ENABLED": True,

    # Which analyzers to run (all enabled by default)
    "ANALYZERS": [
        "query_doctor.analyzers.NPlusOneAnalyzer",
        "query_doctor.analyzers.DuplicateQueryAnalyzer",
        "query_doctor.analyzers.MissingIndexAnalyzer",
        "query_doctor.analyzers.FatSelectAnalyzer",
        "query_doctor.analyzers.QuerySetEvalAnalyzer",
        "query_doctor.analyzers.DRFSerializerAnalyzer",
        "query_doctor.analyzers.QueryComplexityAnalyzer",
    ],

    # Which reporters to use
    "REPORTERS": [
        "query_doctor.reporters.ConsoleReporter",
    ],

    # Minimum severity to report (DEBUG, INFO, WARNING, CRITICAL)
    "MIN_SEVERITY": "INFO",

    # N+1 detection threshold
    "NPLUSONE_THRESHOLD": 3,

    # Duplicate query threshold
    "DUPLICATE_THRESHOLD": 2,

    # Query complexity score threshold
    "COMPLEXITY_THRESHOLD": 50,

    # Paths to exclude from analysis
    "EXCLUDE_PATHS": [
        "/admin/",
        "/static/",
        "/__debug__/",
    ],
}
```

## Environment-Based Toggle

!!! tip "Recommended for production"
    Disable the middleware in production and use management commands in CI instead.
```python title="settings.py"
import os

QUERY_DOCTOR = {
    "ENABLED": os.getenv("QUERY_DOCTOR_ENABLED", "false").lower() == "true",
}
```

Or simply control it with `QUERY_DOCTOR_ENABLED = False` in your production settings module.

## Per-Analyzer Configuration

Each analyzer can be configured individually. See the [Analyzers](../analyzers/overview.md) section for per-analyzer options.

## Reporter Configuration

Multiple reporters can be active simultaneously:
```python title="settings.py"
QUERY_DOCTOR = {
    "REPORTERS": [
        "query_doctor.reporters.ConsoleReporter",
        "query_doctor.reporters.JSONReporter",
        "query_doctor.reporters.HTMLReporter",
    ],
    "JSON_OUTPUT_DIR": "reports/",
    "HTML_OUTPUT_DIR": "reports/html/",
}
```

See [Reporters](../reporters/overview.md) for full configuration options.
