"""
CI/CD configuration — strict, fail on any critical issue.
Use with: python manage.py check_queries --fail-on critical
"""

QUERY_DOCTOR = {
    "ENABLED": True,
    "SAMPLE_RATE": 1.0,                    # Check every request in CI
    "REPORTERS": ["json"],                  # Machine-readable for CI parsing
    "ANALYZERS": {
        "nplusone": {"enabled": True, "threshold": 3},
        "duplicate": {"enabled": True, "threshold": 2},
        "missing_index": {"enabled": True},
        "fat_select": {"enabled": True},
        "queryset_eval": {"enabled": True},
        "drf_serializer": {"enabled": True},
        "complexity": {"enabled": True, "threshold": 8},
    },
    "QUERY_BUDGET": {
        "DEFAULT_MAX_QUERIES": 50,
        "DEFAULT_MAX_TIME_MS": 200,
    },
}
