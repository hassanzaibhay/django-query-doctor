"""Query interceptor that wraps database execution to capture SQL queries.

Uses Django's connection.execute_wrapper() mechanism to intercept all SQL
queries without requiring DEBUG=True. Stores captured queries per-thread
using threading.local() for thread safety.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from query_doctor.fingerprint import extract_tables, fingerprint, normalize_sql
from query_doctor.stack_tracer import capture_callsite
from query_doctor.types import CapturedQuery

logger = logging.getLogger("query_doctor")


class QueryInterceptor:
    """Callable that wraps database query execution to capture SQL queries.

    Designed to be used with Django's connection.execute_wrapper() as a
    context manager. Captures query text, parameters, timing, fingerprint,
    and source code callsite for each executed query.
    """

    def __init__(self, capture_stack: bool = True) -> None:
        """Initialize the interceptor.

        Args:
            capture_stack: Whether to capture stack traces for callsite info.
        """
        self._local = threading.local()
        self._capture_stack = capture_stack

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

                self._get_query_list().append(captured)
            except Exception:
                logger.warning(
                    "query_doctor: failed to capture query metadata",
                    exc_info=True,
                )

        return result

    def _get_query_list(self) -> list[CapturedQuery]:
        """Get the thread-local query list, initializing if needed."""
        if not hasattr(self._local, "queries"):
            self._local.queries = []
        return self._local.queries  # type: ignore[no-any-return]

    def get_queries(self) -> list[CapturedQuery]:
        """Return all captured queries for the current thread."""
        return list(self._get_query_list())

    def clear(self) -> None:
        """Reset the captured query list for the current thread."""
        self._local.queries = []
