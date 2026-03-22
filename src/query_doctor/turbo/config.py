"""Configuration parsing for QueryTurbo.

Reads QUERY_DOCTOR['TURBO'] settings and provides defaults.
"""

from __future__ import annotations

from typing import Any

from query_doctor.conf import get_config

TURBO_DEFAULTS: dict[str, Any] = {
    "ENABLED": False,
    "MAX_SIZE": 1024,
    "SKIP_RAW_SQL": True,
    "SKIP_EXTRA": True,
    "SKIP_SUBQUERIES": True,
    "PREPARE_ENABLED": True,
    "PREPARE_THRESHOLD": 5,
    "VALIDATION_THRESHOLD": 3,
}


def get_turbo_config() -> dict[str, Any]:
    """Return the merged turbo configuration.

    Reads QUERY_DOCTOR['TURBO'] from Django settings (via get_config())
    and merges with TURBO_DEFAULTS.
    """
    config = get_config()
    user_turbo: dict[str, Any] = config.get("TURBO", {})
    result = dict(TURBO_DEFAULTS)
    result.update(user_turbo)
    return result


def is_turbo_enabled() -> bool:
    """Check if QueryTurbo is enabled in settings.

    Returns False by default — users must opt in explicitly.
    """
    return bool(get_turbo_config().get("ENABLED", False))
