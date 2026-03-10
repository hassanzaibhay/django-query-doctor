"""Django settings for the test suite."""

from __future__ import annotations

SECRET_KEY = "test-secret-key-not-for-production"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "query_doctor",
    "tests.testapp",
]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
QUERY_DOCTOR: dict[str, object] = {}  # use all defaults
