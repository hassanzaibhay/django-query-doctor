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
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
            ],
        },
    },
]
ROOT_URLCONF = "tests.testapp.urls"
MIDDLEWARE = [
    "query_doctor.QueryDoctorMiddleware",
]
LOGIN_URL = "/accounts/login/"
QUERY_DOCTOR: dict[str, object] = {}  # use all defaults
