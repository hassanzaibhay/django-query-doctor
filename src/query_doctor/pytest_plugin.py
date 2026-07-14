"""Pytest plugin for django-query-doctor.

Provides a ``query_doctor`` fixture that captures and analyzes SQL queries
during a test. The fixture is opt-in by usage: request it as a test argument
and analysis runs for that test only.

Registration:
    The plugin is auto-discovered via the ``pytest11`` entry point
    defined in pyproject.toml.

Usage:
    def test_my_view(query_doctor):
        response = client.get('/api/books/')
        assert query_doctor.issues == 0
        assert query_doctor.total_queries <= 10
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from query_doctor.types import DiagnosisReport

logger = logging.getLogger("query_doctor")


@pytest.fixture()
def query_doctor(request: pytest.FixtureRequest) -> DiagnosisReport:
    """Fixture that captures and analyzes SQL queries during a test.

    Returns a DiagnosisReport that is populated with query data.
    The report is available during the test for assertions.

    Usage:
        def test_optimized(query_doctor):
            list(Book.objects.select_related('author').all())
            assert query_doctor.issues == 0
    """
    from query_doctor.interceptor import QueryInterceptor
    from query_doctor.types import DiagnosisReport

    report = DiagnosisReport()
    interceptor = QueryInterceptor()

    try:
        from django.db import connection

        wrapper_ctx = connection.execute_wrapper(interceptor)
        wrapper_ctx.__enter__()

        def _finalize() -> None:
            """Finalize the report after the test completes."""
            try:
                wrapper_ctx.__exit__(None, None, None)
            except Exception:
                logger.warning(
                    "query_doctor: failed to exit execute_wrapper",
                    exc_info=True,
                )

            try:
                queries = interceptor.get_queries()
                report.captured_queries = queries
                report.total_queries = len(queries)
                report.total_time_ms = sum(q.duration_ms for q in queries)

                _run_analyzers(report, queries)
            except Exception:
                logger.warning(
                    "query_doctor: pytest fixture analysis failed",
                    exc_info=True,
                )

        request.addfinalizer(_finalize)
    except Exception:
        logger.warning(
            "query_doctor: failed to set up pytest fixture",
            exc_info=True,
        )

    return report


def _run_analyzers(report: DiagnosisReport, queries: list[Any]) -> None:
    """Run all enabled analyzers on the captured queries.

    Args:
        report: The report to populate with prescriptions.
        queries: The captured queries to analyze.
    """
    from query_doctor.plugin_api import discover_analyzers

    analyzers = discover_analyzers()

    for analyzer in analyzers:
        try:
            prescriptions = analyzer.analyze(queries)
            report.prescriptions.extend(prescriptions)
        except Exception:
            logger.warning(
                "query_doctor: analyzer %s failed in pytest plugin",
                getattr(analyzer, "name", "unknown"),
                exc_info=True,
            )
