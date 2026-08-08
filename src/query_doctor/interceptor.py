"""Query interceptor that wraps database execution to capture SQL queries.

Uses Django's connection.execute_wrapper() mechanism to intercept all SQL
queries without requiring DEBUG=True. Stores captured queries per-context
using contextvars.ContextVar for both thread and async safety.

Each interceptor owns one ContextVar, so every construction site is expected
to call ``release()`` once it has read the captures. See ``release()`` for what
accumulates otherwise.
"""

from __future__ import annotations

import contextvars
import logging
import time
from typing import Any

from query_doctor.fingerprint import extract_tables, fingerprint, normalize_sql
from query_doctor.stack_tracer import capture_callsite
from query_doctor.types import CapturedQuery

logger = logging.getLogger("query_doctor")

# Global counter ensures each interceptor instance gets a unique ContextVar name.
_interceptor_counter = 0


class QueryInterceptor:
    """Callable that wraps database query execution to capture SQL queries.

    Designed to be used with Django's connection.execute_wrapper() as a
    context manager. Captures query text, parameters, timing, fingerprint,
    and source code callsite for each executed query.

    Each instance maintains its own isolated query list via a unique
    contextvars.ContextVar, ensuring safety in both multi-threaded and
    async (ASGI) deployments.
    """

    def __init__(
        self,
        capture_stack: bool = True,
        exclude_modules: list[str] | None = None,
    ) -> None:
        """Initialize the interceptor.

        Args:
            capture_stack: Whether to capture stack traces for callsite info.
            exclude_modules: Extra path fragments to skip when locating the
                user-code frame, appended to the built-in exclusions. Callers
                supply the ``STACK_TRACE_EXCLUDE`` setting here; the
                interceptor does not read configuration itself.
        """
        global _interceptor_counter
        _interceptor_counter += 1
        self._capture_stack = capture_stack
        self._exclude_modules = exclude_modules
        # Each instance gets its own ContextVar for async isolation.
        self._queries_var: contextvars.ContextVar[list[CapturedQuery] | None] = (
            contextvars.ContextVar(
                f"query_doctor_queries_{_interceptor_counter}",
                default=None,
            )
        )
        # Initialize with a fresh list for this context. The token is kept so
        # ``release()`` can take the entry back out again: ``set()`` stores the
        # variable in the *running* context, and under WSGI that context is the
        # worker thread's own and lives for the life of the process. Dropping
        # the interceptor does not undo it -- the context holds the reference.
        self._token: contextvars.Token[list[CapturedQuery] | None] | None = self._queries_var.set(
            []
        )

    def __call__(
        self,
        execute: Any,
        sql: str,
        params: Any,
        many: bool,
        context: dict[str, Any],
    ) -> Any:
        """Intercept a database query execution.

        Captures query metadata before and after execution. Always calls
        the original execute function and returns its result. Never raises
        exceptions from our analysis code.
        """
        # Always execute the query -- never break the host app
        start = time.perf_counter()
        try:
            result = execute(sql, params, many, context)
        except Exception:
            # Re-raise database exceptions -- those are not ours to handle
            raise
        finally:
            # Capture metadata even if the query raised (for diagnostics)
            try:
                end = time.perf_counter()
                duration_ms = (end - start) * 1000

                callsite = None
                if self._capture_stack:
                    callsite = capture_callsite(self._exclude_modules)

                normalized = normalize_sql(sql)
                fp = fingerprint(sql)
                tables = extract_tables(sql)
                is_select = normalized.lstrip().startswith("select")

                param_tuple: tuple[Any, ...] | None = None
                if params is not None:
                    try:
                        param_tuple = tuple(params)
                    except (TypeError, ValueError):
                        param_tuple = None

                captured = CapturedQuery(
                    sql=sql,
                    params=param_tuple,
                    duration_ms=duration_ms,
                    fingerprint=fp,
                    normalized_sql=normalized,
                    callsite=callsite,
                    is_select=is_select,
                    tables=tables,
                )

                queries = self._queries_var.get()
                if queries is not None:
                    queries.append(captured)
            except Exception:
                logger.warning(
                    "query_doctor: failed to capture query metadata",
                    exc_info=True,
                )

        return result

    def get_queries(self) -> list[CapturedQuery]:
        """Return all captured queries for the current context."""
        queries = self._queries_var.get()
        if queries is None:
            return []
        return list(queries)

    def clear(self) -> None:
        """Reset the captured query list for the current context."""
        self._queries_var.set([])

    def release(self) -> None:
        """Remove this interceptor's entry from the context that created it.

        Call once the captures have been read, at the end of the unit of work
        that built the interceptor -- a request, a task, a management command
        run. Without it every unit leaves one more ``ContextVar`` in the
        ambient context, each holding that unit's full ``CapturedQuery`` list,
        and a long-lived worker accumulates both without bound.

        Idempotent, and never raises. A token is only valid in the context that
        produced it, so a caller that constructs on one thread and finalises on
        another gets a logged no-op rather than a ``ValueError`` in the host
        application's request path.

        After release, ``get_queries()`` reports an empty list.
        """
        token = self._token
        if token is None:
            return
        self._token = None
        try:
            self._queries_var.reset(token)
        except (ValueError, RuntimeError):
            logger.debug(
                "query_doctor: could not release capture storage; the "
                "interceptor was finalized outside the context that built it",
                exc_info=True,
            )


def build_interceptor() -> QueryInterceptor:
    """Construct a ``QueryInterceptor`` from the active configuration.

    Reads ``CAPTURE_STACK_TRACES`` and ``STACK_TRACE_EXCLUDE`` from
    ``get_config()`` and passes them to ``QueryInterceptor.__init__``. This is
    the single construction point every dispatch site uses so the two settings
    are honoured uniformly; the interceptor itself still reads no configuration.

    If configuration cannot be loaded, logs a warning and falls back to the
    packaged defaults (stack capture on, no extra exclusions) so query capture
    never crashes the host application.

    Returns:
        A configured ``QueryInterceptor`` ready for ``execute_wrapper``.
    """
    from query_doctor.conf import get_config

    try:
        config = get_config()
        capture_stack = config.get("CAPTURE_STACK_TRACES", True)
        exclude_modules = config.get("STACK_TRACE_EXCLUDE")
    except Exception:
        logger.warning(
            "query_doctor: failed to load config for interceptor; using defaults",
            exc_info=True,
        )
        return QueryInterceptor()

    return QueryInterceptor(capture_stack=capture_stack, exclude_modules=exclude_modules)
