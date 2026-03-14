"""Celery task integration for django-query-doctor.

Provides a @diagnose_task decorator that wraps Celery tasks (or any callable)
with query diagnosis. Captures all SQL queries during task execution, runs
analyzers, and sends results to configured reporters.

Celery is NOT required. If not installed, the decorator is a passthrough.

Usage:
    from query_doctor.celery_integration import diagnose_task

    @shared_task
    @diagnose_task
    def send_weekly_report():
        users = User.objects.all()
        for user in users:
            user.profile.email  # N+1 detected

    # Or with a callback:
    @shared_task
    @diagnose_task(on_report=lambda r: logger.info(f"Issues: {r.issues}"))
    def process_orders():
        ...
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from typing import Any, TypeVar, overload

from query_doctor.interceptor import QueryInterceptor
from query_doctor.types import DiagnosisReport

logger = logging.getLogger("query_doctor")

F = TypeVar("F", bound=Callable[..., Any])


@overload
def diagnose_task(func: F) -> F: ...


@overload
def diagnose_task(
    *,
    on_report: Callable[[DiagnosisReport], Any] | None = None,
) -> Callable[[F], F]: ...


def diagnose_task(
    func: F | None = None,
    *,
    on_report: Callable[[DiagnosisReport], Any] | None = None,
) -> F | Callable[[F], F]:
    """Decorator that wraps a function with query diagnosis.

    Can be used with or without arguments:
        @diagnose_task
        def my_task(): ...

        @diagnose_task(on_report=my_callback)
        def my_task(): ...

    Args:
        func: The function to wrap (when used without arguments).
        on_report: Optional callback that receives the DiagnosisReport after execution.

    Returns:
        The wrapped function or a decorator.
    """
    if func is not None:
        return _wrap_task(func, on_report=on_report)

    def decorator(fn: F) -> F:
        return _wrap_task(fn, on_report=on_report)

    return decorator


def _wrap_task(
    func: F,
    on_report: Callable[[DiagnosisReport], Any] | None = None,
) -> F:
    """Wrap a function with query interception and diagnosis.

    Args:
        func: The function to wrap.
        on_report: Optional callback for the diagnosis report.

    Returns:
        The wrapped function.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        """Execute the wrapped function with query diagnosis."""
        report = DiagnosisReport()
        interceptor = QueryInterceptor()

        try:
            from django.db import connection

            with connection.execute_wrapper(interceptor):
                result = func(*args, **kwargs)
        except Exception:
            # Still try to analyze what we captured before re-raising
            _finalize_report(interceptor, report, on_report)
            raise

        _finalize_report(interceptor, report, on_report)
        return result

    return wrapper  # type: ignore[return-value]


def _finalize_report(
    interceptor: QueryInterceptor,
    report: DiagnosisReport,
    on_report: Callable[[DiagnosisReport], Any] | None,
) -> None:
    """Finalize the diagnosis report after task execution.

    Args:
        interceptor: The query interceptor with captured queries.
        report: The report to populate.
        on_report: Optional callback to invoke with the report.
    """
    try:
        queries = interceptor.get_queries()
        report.captured_queries = queries
        report.total_queries = len(queries)
        report.total_time_ms = sum(q.duration_ms for q in queries)

        _run_analyzers(report, queries)

        if on_report is not None:
            on_report(report)
    except Exception:
        logger.warning(
            "query_doctor: celery task diagnosis failed",
            exc_info=True,
        )


def _run_analyzers(report: DiagnosisReport, queries: list[Any]) -> None:
    """Run all analyzers on captured queries.

    Args:
        report: The report to populate with prescriptions.
        queries: The captured queries to analyze.
    """
    from query_doctor.analyzers.duplicate import DuplicateAnalyzer
    from query_doctor.analyzers.nplusone import NPlusOneAnalyzer

    analyzers: list[Any] = [NPlusOneAnalyzer(), DuplicateAnalyzer()]

    try:
        from query_doctor.analyzers.missing_index import MissingIndexAnalyzer

        analyzers.append(MissingIndexAnalyzer())
    except Exception:
        pass

    for analyzer in analyzers:
        try:
            prescriptions = analyzer.analyze(queries)
            report.prescriptions.extend(prescriptions)
        except Exception:
            logger.warning(
                "query_doctor: analyzer %s failed in celery task",
                getattr(analyzer, "name", "unknown"),
                exc_info=True,
            )
