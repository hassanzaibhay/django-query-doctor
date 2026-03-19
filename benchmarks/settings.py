"""Minimal Django settings for the benchmark suite.

Self-contained — does not depend on the test suite or any external project.
"""

from __future__ import annotations

SECRET_KEY = "benchmark-secret-key-not-for-production"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "query_doctor",
    "benchmarks",
]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
QUERY_DOCTOR = {
    "TURBO": {
        "ENABLED": True,
        "MAX_SIZE": 2048,
    },
}
