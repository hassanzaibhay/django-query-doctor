"""
Full configuration reference — every option with explanation.
"""

QUERY_DOCTOR = {
    # Master switch — set False to disable all analysis
    "ENABLED": True,
    # Fraction of requests to analyze (0.0 = none, 1.0 = all)
    # Use < 1.0 in production to reduce overhead
    "SAMPLE_RATE": 1.0,
    # Include source file:line in prescriptions
    # Disable if stack traces cause performance issues
    "CAPTURE_STACK_TRACES": True,
    # Analyzer configuration — each can be enabled/disabled independently
    "ANALYZERS": {
        "nplusone": {
            "enabled": True,
            "threshold": 3,  # Min repeated queries to flag as N+1
        },
        "duplicate": {
            "enabled": True,
            "threshold": 2,  # Min identical queries to flag as duplicate
        },
        "missing_index": {
            "enabled": True,
        },
        "fat_select": {
            "enabled": True,
            "threshold": 8,  # Min selected columns to flag as fat SELECT
        },
        "queryset_eval": {
            "enabled": True,
        },
        "serializer_method": {
            "enabled": True,  # Static DRF analysis (check_serializers)
        },
        "complexity": {
            "enabled": True,
            "threshold": 8,  # Complexity score to flag (higher = more tolerant)
        },
    },
    # Active reporters — output destinations for middleware reports.
    # Recognized names: "console", "json", "log" (only these three).
    "REPORTERS": ["console"],
    # Where the "json" reporter writes its report after each analyzed request
    "JSON_REPORT_PATH": None,
    # URL prefixes to skip analysis entirely
    "IGNORE_URLS": [],
    # Defaults for the @query_budget decorator when called without
    # explicit limits — raises QueryBudgetError if exceeded
    "QUERY_BUDGET": {
        "DEFAULT_MAX_QUERIES": None,  # None = no limit
        "DEFAULT_MAX_TIME_MS": None,  # None = no limit
    },
    # Admin dashboard — in-memory ring buffer for recent reports
    "ADMIN_DASHBOARD": {
        "enabled": False,  # Must be explicitly enabled
        # Ring buffer size, read once when the buffer is first used
        "max_reports": 50,
    },
    # Module suffixes check_serializers imports per app when discovering
    # DRF serializers for static analysis
    "AST_ANALYSIS": {
        "SERIALIZER_MODULES": [
            "serializers",
            "api.serializers",
            "api.v1.serializers",
            "api.v2.serializers",
        ],
    },
    # QueryTurbo SQL compilation cache (off by default; see the QueryTurbo guide)
    "TURBO": {
        "ENABLED": False,
    },
    # Extra path fragments to skip when locating the user-code frame
    "STACK_TRACE_EXCLUDE": [],
    # Path to the .queryignore file itself when it is not beside manage.py;
    # None means look for .queryignore at the project root
    "QUERYIGNORE_PATH": None,
}
