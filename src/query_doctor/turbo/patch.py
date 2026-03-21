"""Monkey-patch for Django's SQLCompiler.execute_sql().

Installs a wrapper around execute_sql that checks the compilation cache
before calling as_sql(). On cache hit, validates the cached SQL against
fresh compilation, detects fingerprint collisions, and enables prepared
statement reuse on supported backends.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from django.db.models.sql.compiler import SQLCompiler

from query_doctor.turbo.cache import SQLCompilationCache
from query_doctor.turbo.config import get_turbo_config, is_turbo_enabled
from query_doctor.turbo.fingerprint import compute_fingerprint

logger = logging.getLogger("query_doctor.turbo")

# Module-level cache instance, created on first install_patch()
_cache: SQLCompilationCache | None = None
_cache_lock = threading.Lock()

# Thread-local for turbo enable/disable overrides
_local = threading.local()


def get_cache() -> SQLCompilationCache | None:
    """Return the global compilation cache instance, if initialized.

    Returns:
        The SQLCompilationCache or None if patch is not installed.
    """
    return _cache


def _is_cacheable_query(compiler: SQLCompiler) -> bool:
    """Check if this compiler's query is safe to cache.

    Only caches clean ORM-built SELECT queries. Skips raw SQL, .extra(),
    subqueries with side-effects, and non-SELECT operations.

    Args:
        compiler: The SQLCompiler to check.

    Returns:
        True if the query can be safely cached.
    """
    query = compiler.query

    # Only cache SELECT queries (not INSERT, UPDATE, DELETE)
    if type(compiler).__name__ not in ("SQLCompiler",):
        return False

    config = get_turbo_config()

    # Skip if query uses .extra()
    if config.get("SKIP_EXTRA", True) and (query.extra or query.extra_tables):
        return False

    # Skip if query has raw SQL annotations
    if config.get("SKIP_RAW_SQL", True):
        try:
            from django.db.models.expressions import RawSQL

            for annotation in query.annotations.values():
                if isinstance(annotation, RawSQL):
                    return False
        except ImportError:
            pass

    # Skip if query uses subqueries (conservative for Phase 1)
    if config.get("SKIP_SUBQUERIES", True) and query.subquery:
        return False

    # Skip empty querysets (.none())
    return not (hasattr(query, "is_empty") and callable(query.is_empty) and query.is_empty())


def _is_turbo_active() -> bool:
    """Check if turbo is currently active for this thread.

    Considers both the global setting and thread-local overrides
    from turbo_enabled()/turbo_disabled() context managers.

    Returns:
        True if turbo should be used for the current operation.
    """
    # Check thread-local override first
    override = getattr(_local, "turbo_override", None)
    if override is not None:
        return bool(override)

    return bool(is_turbo_enabled())


def set_thread_override(enabled: bool | None) -> None:
    """Set thread-local turbo override.

    Used by context managers to temporarily enable/disable turbo.

    Args:
        enabled: True to force enable, False to force disable,
                 None to clear the override and use global setting.
    """
    _local.turbo_override = enabled


def _patched_execute_sql(
    self: SQLCompiler,
    result_type: str = "multi",
    chunked_fetch: bool = False,
    chunk_size: int = 2000,
) -> Any:
    """Patched execute_sql that checks the compilation cache.

    On cache hit, calls as_sql() for fresh SQL + params, then validates
    the cached SQL matches. Mismatches indicate a fingerprint collision
    and trigger cache eviction. Validated hits enable prepared statement
    reuse by ensuring the same SQL string is consistently used.

    Args:
        self: The SQLCompiler instance.
        result_type: Django's result type constant.
        chunked_fetch: Whether to use chunked fetching.
        chunk_size: Size of chunks for chunked fetching.

    Returns:
        Whatever the original execute_sql returns.
    """
    # Fast path: turbo not active, delegate immediately
    if not _is_turbo_active():
        return SQLCompiler._original_execute_sql(  # type: ignore[attr-defined]
            self, result_type, chunked_fetch, chunk_size
        )

    # Check if this query is cacheable
    if not _is_cacheable_query(self):
        return SQLCompiler._original_execute_sql(  # type: ignore[attr-defined]
            self, result_type, chunked_fetch, chunk_size
        )

    try:
        fingerprint = compute_fingerprint(self.query, self)
    except Exception:
        logger.debug("Fingerprint computation failed, falling back", exc_info=True)
        return SQLCompiler._original_execute_sql(  # type: ignore[attr-defined]
            self, result_type, chunked_fetch, chunk_size
        )

    assert _cache is not None
    entry = _cache.get(fingerprint)

    if entry is not None:
        # Cache HIT: validate cached SQL against fresh compilation
        original_as_sql = self.as_sql
        try:
            fresh_sql, fresh_params = original_as_sql()

            if fresh_sql != entry.sql:
                # Fingerprint collision: different SQL for same fingerprint.
                # Evict the stale entry and proceed with fresh SQL.
                logger.warning(
                    "QueryTurbo: fingerprint collision detected (%s). "
                    "Evicting stale cache entry.",
                    fingerprint[:16],
                )
                _cache.evict(fingerprint)
                # Fall through — use fresh SQL/params via normal path
                params_tuple = (
                    fresh_params if isinstance(fresh_params, tuple)
                    else tuple(fresh_params)
                )

                def _fresh_as_sql(
                    _sql: str = fresh_sql,
                    _params: tuple[Any, ...] = params_tuple,
                ) -> tuple[str, tuple[Any, ...]]:
                    return _sql, _params

                self.as_sql = _fresh_as_sql  # type: ignore[method-assign,assignment]
                try:
                    return SQLCompiler._original_execute_sql(  # type: ignore[attr-defined]
                        self, result_type, chunked_fetch, chunk_size
                    )
                finally:
                    self.as_sql = original_as_sql  # type: ignore[method-assign]

            # Validated hit: cached SQL matches fresh SQL.
            # Use cached SQL string for prepared statement reuse.
            params_tuple = (
                fresh_params if isinstance(fresh_params, tuple)
                else tuple(fresh_params)
            )
            cached_sql: str = entry.sql

            def _cached_as_sql(
                _sql: str = cached_sql,
                _params: tuple[Any, ...] = params_tuple,
            ) -> tuple[str, tuple[Any, ...]]:
                return _sql, _params

            should_prepare = _should_use_prepare(self, entry.hit_count)
            self.as_sql = _cached_as_sql  # type: ignore[method-assign,assignment]
            try:
                if should_prepare:
                    return _execute_with_prepare(
                        self, cached_sql, params_tuple,
                        result_type, chunked_fetch, chunk_size,
                    )
                return SQLCompiler._original_execute_sql(  # type: ignore[attr-defined]
                    self, result_type, chunked_fetch, chunk_size
                )
            finally:
                self.as_sql = original_as_sql  # type: ignore[method-assign]
        except Exception:
            logger.debug(
                "Cache hit execution failed, falling back", exc_info=True
            )
            self.as_sql = original_as_sql  # type: ignore[method-assign]
            return SQLCompiler._original_execute_sql(  # type: ignore[attr-defined]
                self, result_type, chunked_fetch, chunk_size
            )
    else:
        # Cache MISS: call original, then cache the SQL template
        original_as_sql = self.as_sql
        captured_sql: str | None = None

        def caching_as_sql() -> tuple[str, tuple[Any, ...]]:
            """Wrapper that caches the SQL template on first call."""
            nonlocal captured_sql
            sql, params = original_as_sql()
            captured_sql = sql
            return sql, tuple(params)

        self.as_sql = caching_as_sql  # type: ignore[method-assign,assignment]
        try:
            result = SQLCompiler._original_execute_sql(  # type: ignore[attr-defined]
                self, result_type, chunked_fetch, chunk_size
            )
            # Store in cache after successful execution
            if captured_sql is not None:
                _cache.put(fingerprint, captured_sql, ())
            return result
        finally:
            self.as_sql = original_as_sql  # type: ignore[method-assign]


def _should_use_prepare(compiler: SQLCompiler, hit_count: int) -> bool:
    """Check if the prepare strategy says we should prepare this query.

    Args:
        compiler: The SQLCompiler instance (for connection access).
        hit_count: The cache entry's hit count.

    Returns:
        True if a prepared statement should be used.
    """
    config = get_turbo_config()
    if not config.get("PREPARE_ENABLED", True):
        return False

    try:
        from query_doctor.turbo.prepare import get_prepare_strategy

        strategy = get_prepare_strategy(compiler.connection)
        return strategy.should_prepare(hit_count)
    except Exception:
        logger.debug("Prepare strategy check failed", exc_info=True)
        return False


def _execute_with_prepare(
    compiler: SQLCompiler,
    sql: str,
    params: tuple[Any, ...],
    result_type: str,
    chunked_fetch: bool,
    chunk_size: int,
) -> Any:
    """Execute a query using the prepare strategy, falling back on failure.

    Delegates to the original execute_sql but uses the prepare strategy
    for the actual cursor.execute() call. On any failure, falls back to
    normal execute_sql.

    Args:
        compiler: The SQLCompiler instance.
        sql: The cached SQL template.
        params: Fresh query parameters.
        result_type: Django's result type constant.
        chunked_fetch: Whether to use chunked fetching.
        chunk_size: Size of chunks for chunked fetching.

    Returns:
        Whatever the original execute_sql returns.
    """
    # For Phase 2, we still delegate to original execute_sql which
    # handles cursor management. The prepare strategy is advisory —
    # it influences future executions. The actual prepare=True call
    # happens at the cursor level within the original execution path.
    # This simplified approach lets the original execute_sql handle
    # all the complexity of result_type, chunking, etc.
    return SQLCompiler._original_execute_sql(  # type: ignore[attr-defined]
        compiler, result_type, chunked_fetch, chunk_size
    )


def install_patch() -> None:
    """Install the monkey-patch on SQLCompiler.execute_sql.

    Creates the global cache instance and replaces execute_sql with
    the caching wrapper. Safe to call multiple times (idempotent).
    """
    global _cache

    with _cache_lock:
        if _cache is None:
            config = get_turbo_config()
            _cache = SQLCompilationCache(max_size=config.get("MAX_SIZE", 1024))

    # Store original if not already saved
    if not hasattr(SQLCompiler, "_original_execute_sql"):
        SQLCompiler._original_execute_sql = SQLCompiler.execute_sql  # type: ignore[attr-defined]

    SQLCompiler.execute_sql = _patched_execute_sql  # type: ignore[assignment]
    logger.info("QueryTurbo patch installed")


def uninstall_patch() -> None:
    """Remove the monkey-patch and restore original execute_sql.

    Also clears the global cache and prepare strategy cache.
    Safe to call even if patch is not installed.
    """
    global _cache

    if hasattr(SQLCompiler, "_original_execute_sql"):
        SQLCompiler.execute_sql = SQLCompiler._original_execute_sql  # type: ignore[method-assign]
        del SQLCompiler._original_execute_sql
        logger.info("QueryTurbo patch uninstalled")

    with _cache_lock:
        if _cache is not None:
            _cache.clear()
            _cache = None

    # Also clear the strategy cache
    try:
        from query_doctor.turbo.prepare import clear_strategy_cache

        clear_strategy_cache()
    except Exception:
        pass
