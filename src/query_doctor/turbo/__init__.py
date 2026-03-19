"""QueryTurbo: SQL compilation cache for Django ORM queries.

Intercepts Django's SQLCompiler.execute_sql(), fingerprints the Query tree
structure (excluding parameter values), caches the compiled SQL template on
first compilation, and reuses it on subsequent calls with identical structure.
"""

from __future__ import annotations

from query_doctor.turbo.cache import SQLCompilationCache
from query_doctor.turbo.context import turbo_disabled, turbo_enabled
from query_doctor.turbo.patch import install_patch, uninstall_patch

__all__ = [
    "SQLCompilationCache",
    "install_patch",
    "turbo_disabled",
    "turbo_enabled",
    "uninstall_patch",
]
