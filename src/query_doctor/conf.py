"""Configuration management for django-query-doctor.

Provides get_config() to retrieve the merged configuration from
Django settings and built-in defaults. All other modules should
access settings through this module only.
"""

from __future__ import annotations

import copy
import functools
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    "ENABLED": True,
    "SAMPLE_RATE": 1.0,
    "CAPTURE_STACK_TRACES": True,
    "STACK_TRACE_EXCLUDE": [],
    "ANALYZERS": {
        "nplusone": {"enabled": True, "threshold": 3},
        "duplicate": {"enabled": True, "threshold": 2},
        "missing_index": {"enabled": True},
        "fat_select": {"enabled": True},
        "queryset_eval": {"enabled": True},
        "drf_serializer": {"enabled": True},
        "complexity": {"enabled": True, "threshold": 8},
    },
    "REPORTERS": ["console"],
    "IGNORE_PATTERNS": [],
    "IGNORE_URLS": [],
    "QUERY_BUDGET": {"DEFAULT_MAX_QUERIES": None, "DEFAULT_MAX_TIME_MS": None},
    "ADMIN_DASHBOARD": {"enabled": False, "max_reports": 50},
    "QUERYIGNORE_PATH": None,
    "TURBO": {
        "ENABLED": False,
        "MAX_SIZE": 1024,
        "SKIP_RAW_SQL": True,
        "SKIP_EXTRA": True,
        "SKIP_SUBQUERIES": True,
        "PREPARE_ENABLED": True,
        "PREPARE_THRESHOLD": 5,
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge override into base, returning a new dict.

    Nested dicts are merged recursively. All other types are replaced.
    """
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


@functools.lru_cache(maxsize=1)
def get_config() -> dict[str, Any]:
    """Return the merged configuration, cached after first call.

    Reads the QUERY_DOCTOR setting from Django settings and deep-merges
    it with DEFAULT_CONFIG. The result is cached for performance.
    """
    from django.conf import settings

    user_config: dict[str, Any] = getattr(settings, "QUERY_DOCTOR", {})
    return _deep_merge(DEFAULT_CONFIG, user_config)
