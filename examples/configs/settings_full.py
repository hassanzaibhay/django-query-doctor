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

    # Module prefixes to exclude from stack trace capture
    # Useful for filtering out middleware, libraries, etc.
    "STACK_TRACE_EXCLUDE": [],

    # Analyzer configuration — each can be enabled/disabled independently
    "ANALYZERS": {
        "nplusone": {
            "enabled": True,
            "threshold": 3,     # Min repeated queries to flag as N+1
        },
        "duplicate": {
            "enabled": True,
            "threshold": 2,     # Min identical queries to flag as duplicate
        },
        "missing_index": {
            "enabled": True,
        },
        "fat_select": {
            "enabled": True,
        },
        "queryset_eval": {
            "enabled": True,
        },
        "drf_serializer": {
            "enabled": True,
        },
        "complexity": {
            "enabled": True,
            "threshold": 8,     # Complexity score to flag (higher = more tolerant)
        },
    },

    # Active reporters — output destinations for diagnosis results
    # Options: "console", "json", "log", "html", "otel"
    "REPORTERS": ["console"],

    # SQL patterns to exclude from analysis (SQL LIKE syntax, % = wildcard)
    "IGNORE_PATTERNS": [],

    # URL prefixes to skip analysis entirely
    "IGNORE_URLS": [],

    # Global query budgets — raises QueryBudgetError if exceeded
    "QUERY_BUDGET": {
        "DEFAULT_MAX_QUERIES": None,     # None = no limit
        "DEFAULT_MAX_TIME_MS": None,     # None = no limit
    },

    # Admin dashboard — in-memory ring buffer for recent reports
    "ADMIN_DASHBOARD": {
        "enabled": False,       # Must be explicitly enabled
        "max_reports": 50,      # Number of recent reports to keep
    },

    # Custom .queryignore file path (default: auto-detect at project root)
    "QUERYIGNORE_PATH": None,
}
