"""
Minimal Django settings for query-doctor example project.
This is a self-contained single-folder Django project.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SECRET_KEY = "example-insecure-key-for-demo-only"
DEBUG = True
ALLOWED_HOSTS = ["*"]
ROOT_URLCONF = "urls"

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

MIDDLEWARE = [
    "query_doctor.QueryDoctorMiddleware",
]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": False,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
            ],
        },
    },
]

QUERY_DOCTOR = {
    "ENABLED": True,
    "REPORTERS": ["console"],
    "ANALYZERS": {
        "nplusone": {"enabled": True, "threshold": 3},
        "duplicate": {"enabled": True, "threshold": 2},
        "missing_index": {"enabled": True},
        "fat_select": {"enabled": True},
        "queryset_eval": {"enabled": True},
        "drf_serializer": {"enabled": True},
        "complexity": {"enabled": True, "threshold": 8},
    },
}
