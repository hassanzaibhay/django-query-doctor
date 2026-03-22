"""Query interceptor that wraps database execution to capture SQL queries.

Uses Django's connection.execute_wrapper() mechanism to intercept all SQL
queries without requiring DEBUG=True. Stores captured queries per-context
using contextvars.ContextVar for both thread and async safety.
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

    def __init__(self, capture_stack: bool = True) -> None:
        """Initialize the interceptor.

        Args:
            capture_stack: Whether to capture stack traces for callsite info.
        """
        global _interceptor_counter
        _interceptor_counter += 1
        self._capture_stack = capture_stack
        # Each instance gets its own ContextVar for async isolation.
        self._queries_var: contextvars.ContextVar[list[CapturedQuery] | None] = (
            contextvars.ContextVar(
                f"query_doctor_queries_{_interceptor_counter}",
                default=None,
            )
        )
        # Initialize with a fresh list for this context.
        self._queries_var.set([])

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
        # Always execute the query — never break the host app
        start = time.perf_counter()
        try:
            result = execute(sql, params, many, context)
        except Exception:
            # Re-raise database exceptions — those are not ours to handle
            raise
        finally:
            # Capture metadata even if the query raised (for diagnostics)
            try:
                end = time.perf_counter()
                duration_ms = (end - start) * 1000

                callsite = None
                if self._capture_stack:
                    callsite = capture_callsite()

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
