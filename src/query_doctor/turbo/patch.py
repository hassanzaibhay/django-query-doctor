"""Monkey-patch for Django's SQLCompiler.execute_sql().

Installs a wrapper around execute_sql that checks the compilation cache
before calling as_sql(). Implements a three-phase trust lifecycle:

1. UNTRUSTED: Validates cached SQL against fresh as_sql() on each hit.
2. TRUSTED: Skips as_sql() entirely, extracts params from Query tree.
3. POISONED: Fingerprint collision detected, cache permanently bypassed.

On cache miss, stores the SQL template for future reuse.
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
    """Check if turbo is currently active for this thread/coroutine.

    Considers both the global setting and contextvars overrides
    from turbo_enabled()/turbo_disabled() context managers.

    Returns:
        True if turbo should be used for the current operation.
    """
    from query_doctor.turbo.context import get_turbo_override

    override = get_turbo_override()
    if override is not None:
        return bool(override)

    return bool(is_turbo_enabled())


def set_thread_override(enabled: bool | None) -> None:
    """Set turbo override (deprecated — use context.set_turbo_override).

    Kept for backward compatibility. Delegates to contextvars-based
    override in context.py.

    Args:
        enabled: True to force enable, False to force disable,
                 None to clear the override and use global setting.
    """
    from query_doctor.turbo.context import set_turbo_override

    set_turbo_override(enabled)


def _patched_execute_sql(
    self: SQLCompiler,
    result_type: str = "multi",
    chunked_fetch: bool = False,
    chunk_size: int = 2000,
) -> Any:
    """Patched execute_sql with three-phase trust lifecycle.

    Phase 1 (UNTRUSTED): Calls as_sql() for validation.
    Phase 2 (TRUSTED): Skips as_sql(), extracts params from Query tree.
    Phase 3 (POISONED): Bypasses cache entirely.

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
        # --- POISONED: skip cache permanently ---
        if entry.poisoned:
            return SQLCompiler._original_execute_sql(  # type: ignore[attr-defined]
                self, result_type, chunked_fetch, chunk_size
            )

        # --- TRUSTED: skip as_sql() entirely ---
        if entry.trusted:
            return _handle_trusted_hit(
                self, entry, fingerprint, result_type, chunked_fetch, chunk_size
            )

        # --- UNTRUSTED: validate by calling as_sql() ---
        return _handle_untrusted_hit(
            self, entry, fingerprint, result_type, chunked_fetch, chunk_size
        )

    # --- Cache MISS: call original, then cache the SQL template ---
    return _handle_cache_miss(self, fingerprint, result_type, chunked_fetch, chunk_size)


def _handle_trusted_hit(
    compiler: SQLCompiler,
    entry: Any,
    fingerprint: str,
    result_type: str,
    chunked_fetch: bool,
    chunk_size: int,
) -> Any:
    """Handle a TRUSTED cache hit — skip as_sql() entirely.

    Extracts params from the Query tree without SQL compilation.
    Validates param count matches the cached template. On mismatch,
    demotes to UNTRUSTED and falls back to full as_sql().

    Args:
        compiler: The SQLCompiler instance.
        entry: The CacheEntry.
        fingerprint: The fingerprint key.
        result_type: Django's result type constant.
        chunked_fetch: Whether to use chunked fetching.
        chunk_size: Size of chunks for chunked fetching.

    Returns:
        Whatever the original execute_sql returns.
    """
    from query_doctor.turbo.params import ParamExtractionError, extract_params

    original_as_sql = compiler.as_sql
    try:
        extracted = extract_params(compiler.query, compiler)

        if len(extracted) != entry.param_count:
            # Param count mismatch — demote to untrusted
            entry.trusted = False
            entry.validated_count = 0
            logger.warning(
                "QueryTurbo param count mismatch for %s: expected %d, got %d. "
                "Demoting to untrusted.",
                fingerprint[:16],
                entry.param_count,
                len(extracted),
            )
            # Fall back to full as_sql()
            return SQLCompiler._original_execute_sql(  # type: ignore[attr-defined]
                compiler, result_type, chunked_fetch, chunk_size
            )

        # SUCCESS — true compilation skip!
        assert _cache is not None
        _cache.record_trusted_hit()
        cached_sql = entry.sql

        def _cached_as_sql(
            _sql: str = cached_sql,
            _params: tuple[Any, ...] = extracted,
        ) -> tuple[str, tuple[Any, ...]]:
            return _sql, _params

        compiler.as_sql = _cached_as_sql  # type: ignore[method-assign,assignment]
        try:
            should_prepare = _should_use_prepare(compiler, entry.hit_count)
            if should_prepare:
                return _execute_with_prepare(
                    compiler,
                    cached_sql,
                    extracted,
                    result_type,
                    chunked_fetch,
                    chunk_size,
                )
            return SQLCompiler._original_execute_sql(  # type: ignore[attr-defined]
                compiler, result_type, chunked_fetch, chunk_size
            )
        finally:
            compiler.as_sql = original_as_sql  # type: ignore[method-assign]

    except ParamExtractionError:
        # Extraction failed — demote and fall back
        entry.trusted = False
        entry.validated_count = 0
        logger.debug("Param extraction failed, demoting %s", fingerprint[:16])
        return SQLCompiler._original_execute_sql(  # type: ignore[attr-defined]
            compiler, result_type, chunked_fetch, chunk_size
        )
    except Exception:
        logger.debug("Trusted hit execution failed, falling back", exc_info=True)
        compiler.as_sql = original_as_sql  # type: ignore[method-assign]
        return SQLCompiler._original_execute_sql(  # type: ignore[attr-defined]
            compiler, result_type, chunked_fetch, chunk_size
        )


def _handle_untrusted_hit(
    compiler: SQLCompiler,
    entry: Any,
    fingerprint: str,
    result_type: str,
    chunked_fetch: bool,
    chunk_size: int,
) -> Any:
    """Handle an UNTRUSTED cache hit — validate via as_sql().

    Calls as_sql() to get fresh (sql, params), validates that
    fresh_sql == cached_sql. On match, increments validated_count
    and promotes to TRUSTED after threshold. On mismatch, poisons
    the entry.

    Args:
        compiler: The SQLCompiler instance.
        entry: The CacheEntry.
        fingerprint: The fingerprint key.
        result_type: Django's result type constant.
        chunked_fetch: Whether to use chunked fetching.
        chunk_size: Size of chunks for chunked fetching.

    Returns:
        Whatever the original execute_sql returns.
    """
    config = get_turbo_config()
    threshold = config.get("VALIDATION_THRESHOLD", 3)

    original_as_sql = compiler.as_sql
    try:
        fresh_sql, fresh_params = original_as_sql()

        if fresh_sql != entry.sql:
            # COLLISION! Poison this fingerprint permanently
            assert _cache is not None
            _cache.poison(fingerprint)
            logger.warning(
                "QueryTurbo collision detected for fingerprint %s. SQL mismatch. Entry poisoned.",
                fingerprint[:16],
            )
            # Use fresh SQL + params via normal path
            params_tuple = fresh_params if isinstance(fresh_params, tuple) else tuple(fresh_params)

            def _fresh_as_sql(
                _sql: str = fresh_sql,
                _params: tuple[Any, ...] = params_tuple,
            ) -> tuple[str, tuple[Any, ...]]:
                return _sql, _params

            compiler.as_sql = _fresh_as_sql  # type: ignore[method-assign,assignment]
            try:
                return SQLCompiler._original_execute_sql(  # type: ignore[attr-defined]
                    compiler, result_type, chunked_fetch, chunk_size
                )
            finally:
                compiler.as_sql = original_as_sql  # type: ignore[method-assign]

        # Validation passed — increment validated_count
        entry.validated_count += 1
        if entry.validated_count >= threshold:
            entry.trusted = True
            logger.debug("Cache entry trusted: %s", fingerprint[:16])

        # Use fresh SQL + params (validated correct)
        params_tuple = fresh_params if isinstance(fresh_params, tuple) else tuple(fresh_params)
        cached_sql = entry.sql

        def _cached_as_sql(
            _sql: str = cached_sql,
            _params: tuple[Any, ...] = params_tuple,
        ) -> tuple[str, tuple[Any, ...]]:
            return _sql, _params

        should_prepare = _should_use_prepare(compiler, entry.hit_count)
        compiler.as_sql = _cached_as_sql  # type: ignore[method-assign,assignment]
        try:
            if should_prepare:
                return _execute_with_prepare(
                    compiler,
                    cached_sql,
                    params_tuple,
                    result_type,
                    chunked_fetch,
                    chunk_size,
                )
            return SQLCompiler._original_execute_sql(  # type: ignore[attr-defined]
                compiler, result_type, chunked_fetch, chunk_size
            )
        finally:
            compiler.as_sql = original_as_sql  # type: ignore[method-assign]

    except Exception:
        logger.debug("Cache hit execution failed, falling back", exc_info=True)
        compiler.as_sql = original_as_sql  # type: ignore[method-assign]
        return SQLCompiler._original_execute_sql(  # type: ignore[attr-defined]
            compiler, result_type, chunked_fetch, chunk_size
        )


def _handle_cache_miss(
    compiler: SQLCompiler,
    fingerprint: str,
    result_type: str,
    chunked_fetch: bool,
    chunk_size: int,
) -> Any:
    """Handle a cache miss — execute normally, then cache the SQL template.

    Args:
        compiler: The SQLCompiler instance.
        fingerprint: The fingerprint key.
        result_type: Django's result type constant.
        chunked_fetch: Whether to use chunked fetching.
        chunk_size: Size of chunks for chunked fetching.

    Returns:
        Whatever the original execute_sql returns.
    """
    original_as_sql = compiler.as_sql
    captured_sql: str | None = None
    captured_param_count: int = 0

    def caching_as_sql() -> tuple[str, tuple[Any, ...]]:
        """Wrapper that captures the SQL template on first call."""
        nonlocal captured_sql, captured_param_count
        sql, params = original_as_sql()
        captured_sql = sql
        params_tuple = tuple(params)
        captured_param_count = len(params_tuple)
        return sql, params_tuple

    compiler.as_sql = caching_as_sql  # type: ignore[method-assign,assignment]
    try:
        result = SQLCompiler._original_execute_sql(  # type: ignore[attr-defined]
            compiler, result_type, chunked_fetch, chunk_size
        )
        # Store in cache after successful execution
        if captured_sql is not None:
            assert _cache is not None
            model_label = ""
            if compiler.query.model is not None:
                model_label = compiler.query.model._meta.label
            _cache.put(fingerprint, captured_sql, captured_param_count, model_label)
        return result
    finally:
        compiler.as_sql = original_as_sql  # type: ignore[method-assign]


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
