"""
Production-recommended configuration.
Sample at 10% of requests, use JSON reporter for log aggregation.
"""

QUERY_DOCTOR = {
    "ENABLED": True,
    "SAMPLE_RATE": 0.1,                    # Analyze 10% of requests
    "CAPTURE_STACK_TRACES": True,
    "REPORTERS": ["log", "json"],           # Machine-readable output
    "IGNORE_URLS": [
        "/admin/",
        "/health/",
        "/metrics/",
        "/static/",
        "/__debug__/",
    ],
    "ANALYZERS": {
        "nplusone": {"enabled": True, "threshold": 5},    # Higher threshold in prod
        "duplicate": {"enabled": True, "threshold": 3},
        "missing_index": {"enabled": True},
        "fat_select": {"enabled": False},                   # Too noisy in prod
        "queryset_eval": {"enabled": True},
        "drf_serializer": {"enabled": True},
        "complexity": {"enabled": True, "threshold": 10},  # Higher threshold
    },
    "QUERY_BUDGET": {
        "DEFAULT_MAX_QUERIES": 100,
        # Alert if any request exceeds 100 queries
        "DEFAULT_MAX_TIME_MS": 500,
        # Alert if queries take > 500ms total
    },
}
