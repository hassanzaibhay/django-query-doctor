"""Decorators for query diagnosis and budget enforcement.

Provides @diagnose for wrapping functions with automatic query analysis,
and @query_budget for enforcing query count and time limits.
"""

from __future__ import annotations

import functools
import logging
from typing import Any, TypeVar

from query_doctor.conf import get_config
from query_doctor.context_managers import diagnose_queries
from query_doctor.exceptions import QueryBudgetError
from query_doctor.types import DiagnosisReport

logger = logging.getLogger("query_doctor")

F = TypeVar("F")


def _get_report_time_ms(report: DiagnosisReport) -> float:
    """Return total query time from a report.

    Extracted to a module-level function for testability (can be patched).
    """
    return report.total_time_ms


def diagnose(func: Any) -> Any:
    """Decorator that diagnoses queries executed within a function.

    Wraps the function with diagnose_queries() context manager. After
    execution, the DiagnosisReport is attached as func._query_doctor_report.

    Usage:
        @diagnose
        def my_view(request):
            return Book.objects.all()
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        """Execute the wrapped function with query diagnosis."""
        try:
            with diagnose_queries() as report:
                result = func(*args, **kwargs)
        except QueryBudgetError:
            raise
        except Exception:
            # If diagnose_queries itself fails to set up, run without diagnosis
            logger.warning(
                "query_doctor: @diagnose failed, running function without diagnosis",
                exc_info=True,
            )
            return func(*args, **kwargs)

        wrapper._query_doctor_report = report  # type: ignore[attr-defined]
        return result

    return wrapper


def query_budget(
    max_queries: int | None = None,
    max_time_ms: float | None = None,
) -> Any:
    """Decorator that enforces query budget limits on a function.

    Raises QueryBudgetError if the function exceeds the specified
    query count or time limits. Falls back to config defaults if no
    explicit limits are provided.

    Args:
        max_queries: Maximum number of queries allowed. None means no limit.
        max_time_ms: Maximum total query time in milliseconds. None means no limit.

    Usage:
        @query_budget(max_queries=10, max_time_ms=100)
        def my_view(request):
            return Book.objects.all()
    """

    def decorator(func: Any) -> Any:
        """Wrap the function with budget enforcement."""

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            """Execute the wrapped function with budget checking."""
            # Resolve limits: explicit args take priority over config
            config = get_config()
            budget_config = config.get("QUERY_BUDGET", {})
            effective_max_queries = (
                max_queries
                if max_queries is not None
                else budget_config.get("DEFAULT_MAX_QUERIES")
            )
            effective_max_time_ms = (
                max_time_ms
                if max_time_ms is not None
                else budget_config.get("DEFAULT_MAX_TIME_MS")
            )

            with diagnose_queries() as report:
                result = func(*args, **kwargs)

            wrapper._query_doctor_report = report  # type: ignore[attr-defined]

            # Check budget after execution
            if effective_max_queries is not None and report.total_queries > effective_max_queries:
                raise QueryBudgetError(
                    f"Query budget exceeded: {report.total_queries} queries "
                    f"(max_queries={effective_max_queries})",
                    report=report,
                )

            report_time = _get_report_time_ms(report)
            if effective_max_time_ms is not None and report_time > effective_max_time_ms:
                raise QueryBudgetError(
                    f"Query budget exceeded: {report_time:.1f}ms "
                    f"(max_time_ms={effective_max_time_ms})",
                    report=report,
                )

            return result

        return wrapper

    return decorator
