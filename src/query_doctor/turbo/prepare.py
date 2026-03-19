"""Prepared statement bridge with backend-adaptive strategies.

Detects the database driver and enables prepared statements where supported.
The SQL compilation cache from Phase 1 already reuses identical SQL strings —
this module leverages that for automatic preparation after a hit-count threshold.

Supported backends:
- PostgreSQL (psycopg3): Protocol-level prepared statements via prepare=True.
- Oracle (cx_Oracle/oracledb): Implicit statement caching via SQL string reuse.
- MySQL, SQLite, others: No preparation (NoPrepareStrategy fallback).
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Protocol

logger = logging.getLogger("query_doctor.turbo")

# Module-level strategy cache: vendor string → strategy instance.
# Protected by _strategy_lock for thread-safe lazy initialization.
_strategy_cache: dict[str, PrepareStrategy] = {}
_strategy_lock = threading.Lock()


class PrepareStrategy(Protocol):
    """Protocol for database-specific prepared statement strategies."""

    def should_prepare(self, hit_count: int) -> bool:
        """Return True if the query should use a prepared statement.

        Args:
            hit_count: Number of cache hits for this query pattern.
        """
        ...  # pragma: no cover

    def execute(
        self,
        cursor: Any,
        sql: str,
        params: tuple[Any, ...] | None,
        *,
        prepare: bool = False,
    ) -> None:
        """Execute SQL on the cursor, optionally as a prepared statement.

        Must never raise — falls back to normal execute on any error.

        Args:
            cursor: The database cursor.
            sql: The SQL string to execute.
            params: Query parameters.
            prepare: Whether to attempt prepared statement execution.
        """
        ...  # pragma: no cover


class NoPrepareStrategy:
    """Fallback strategy for backends without prepared statement support.

    Used for MySQL (mysqlclient), SQLite, psycopg2, and any other backend
    that does not support protocol-level prepared statements.
    """

    def should_prepare(self, hit_count: int) -> bool:
        """Always returns False — no preparation support.

        Args:
            hit_count: Number of cache hits (ignored).

        Returns:
            Always False.
        """
        return False

    def execute(
        self,
        cursor: Any,
        sql: str,
        params: tuple[Any, ...] | None,
        *,
        prepare: bool = False,
    ) -> None:
        """Execute SQL normally without preparation.

        Args:
            cursor: The database cursor.
            sql: The SQL string to execute.
            params: Query parameters.
            prepare: Ignored for this strategy.
        """
        cursor.execute(sql, params)


class PsycopgPrepareStrategy:
    """Strategy for PostgreSQL with psycopg3 (psycopg).

    After a cache entry's hit_count exceeds the threshold, passes
    prepare=True to cursor.execute(). psycopg3 then uses protocol-level
    PQsendPrepare/PQsendQueryPrepared for optimal performance.

    If prepare=True raises TypeError (wrong driver version), falls back
    to normal execute and disables preparation for this instance.
    """

    def __init__(self, threshold: int = 5) -> None:
        """Initialize with a preparation threshold.

        Args:
            threshold: Minimum cache hits before preparing statements.
        """
        self._threshold = threshold
        self._prepare_disabled = False

    def should_prepare(self, hit_count: int) -> bool:
        """Return True if hit_count exceeds the threshold and prepare is not disabled.

        Args:
            hit_count: Number of cache hits for this query pattern.

        Returns:
            True if the statement should be prepared.
        """
        if self._prepare_disabled:
            return False
        return hit_count >= self._threshold

    def execute(
        self,
        cursor: Any,
        sql: str,
        params: tuple[Any, ...] | None,
        *,
        prepare: bool = False,
    ) -> None:
        """Execute SQL, optionally with psycopg3 prepare=True.

        If prepare=True raises TypeError (incompatible driver), disables
        preparation for all future calls on this strategy instance and
        falls back to normal execution.

        Args:
            cursor: The database cursor.
            sql: The SQL string to execute.
            params: Query parameters.
            prepare: Whether to use prepared statement execution.
        """
        if prepare and not self._prepare_disabled:
            try:
                cursor.execute(sql, params, prepare=prepare)
                return
            except TypeError:
                logger.info(
                    "psycopg cursor does not support prepare=True, "
                    "disabling prepared statements"
                )
                self._prepare_disabled = True
            except Exception:
                logger.debug(
                    "Prepared statement execution failed, falling back",
                    exc_info=True,
                )
        cursor.execute(sql, params)


class OracleImplicitCacheStrategy:
    """Strategy for Oracle databases (cx_Oracle / oracledb).

    Oracle's client library has implicit statement caching. By reusing
    identical SQL strings (which our compilation cache already does),
    Oracle's internal cache hits automatically. This strategy simply
    logs that Oracle implicit caching is active — no special execute call.
    """

    _logged_once: bool = False
    _log_lock: threading.Lock = threading.Lock()

    def should_prepare(self, hit_count: int) -> bool:
        """Always returns False — Oracle handles caching implicitly.

        Uses double-check locking for thread-safe one-time logging.

        Args:
            hit_count: Number of cache hits (ignored).

        Returns:
            Always False.
        """
        if not self._logged_once:
            with OracleImplicitCacheStrategy._log_lock:
                if not OracleImplicitCacheStrategy._logged_once:
                    logger.info(
                        "Oracle implicit statement caching is active via SQL string reuse"
                    )
                    OracleImplicitCacheStrategy._logged_once = True
        return False

    def execute(
        self,
        cursor: Any,
        sql: str,
        params: tuple[Any, ...] | None,
        *,
        prepare: bool = False,
    ) -> None:
        """Execute SQL normally — Oracle handles caching implicitly.

        Args:
            cursor: The database cursor.
            sql: The SQL string to execute.
            params: Query parameters.
            prepare: Ignored for this strategy.
        """
        cursor.execute(sql, params)


def get_prepare_strategy(connection: Any) -> PrepareStrategy:
    """Detect and return the appropriate prepare strategy for a database connection.

    Strategy instances are cached per connection.vendor so detection happens
    only once per backend type within the process lifetime.

    Args:
        connection: A Django database connection object.

    Returns:
        A PrepareStrategy appropriate for the connection's database backend.
    """
    from query_doctor.turbo.config import get_turbo_config

    config = get_turbo_config()

    # If prepare is globally disabled, always return NoPrepareStrategy
    if not config.get("PREPARE_ENABLED", True):
        return NoPrepareStrategy()

    vendor = connection.vendor

    with _strategy_lock:
        if vendor in _strategy_cache:
            return _strategy_cache[vendor]

        strategy = _detect_strategy(vendor, config)
        _strategy_cache[vendor] = strategy
        return strategy


def _detect_strategy(vendor: str, config: dict[str, Any]) -> PrepareStrategy:
    """Detect the best prepare strategy for a given database vendor.

    Args:
        vendor: The database vendor string (e.g., 'postgresql', 'oracle').
        config: The turbo configuration dictionary.

    Returns:
        The appropriate PrepareStrategy instance.
    """
    threshold = config.get("PREPARE_THRESHOLD", 5)

    if vendor == "postgresql":
        try:
            import psycopg  # type: ignore[import-not-found]  # noqa: F401

            logger.info("PostgreSQL with psycopg3 detected, enabling prepared statements")
            return PsycopgPrepareStrategy(threshold=threshold)
        except ImportError:
            logger.debug("psycopg3 not available, using NoPrepareStrategy for PostgreSQL")
            return NoPrepareStrategy()

    elif vendor == "oracle":
        logger.info("Oracle detected, using implicit statement caching strategy")
        return OracleImplicitCacheStrategy()

    # MySQL (mysqlclient), SQLite, others
    return NoPrepareStrategy()


def clear_strategy_cache() -> None:
    """Clear the module-level strategy cache.

    Used during testing or when configuration changes require re-detection.
    """
    with _strategy_lock:
        _strategy_cache.clear()
        OracleImplicitCacheStrategy._logged_once = False
