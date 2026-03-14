"""Context managers for targeted query diagnosis.

Provides diagnose_queries() for diagnosing queries within a specific
code block rather than an entire request.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager

from query_doctor.analyzers.duplicate import DuplicateAnalyzer
from query_doctor.analyzers.missing_index import MissingIndexAnalyzer
from query_doctor.analyzers.nplusone import NPlusOneAnalyzer
from query_doctor.interceptor import QueryInterceptor
from query_doctor.types import DiagnosisReport

logger = logging.getLogger("query_doctor")


@contextmanager
def diagnose_queries() -> Generator[DiagnosisReport, None, None]:
    """Context manager for targeted query diagnosis.

    Captures and analyzes all SQL queries executed within the context.
    The DiagnosisReport is yielded and populated after the context exits.

    Usage:
        with diagnose_queries() as report:
            # ... your ORM code here ...
        print(report.issues)
    """
    report = DiagnosisReport()
    interceptor = QueryInterceptor()

    from django.db import connection

    with connection.execute_wrapper(interceptor):
        yield report

    # After context exits, run analysis
    try:
        queries = interceptor.get_queries()
        report.captured_queries = queries
        report.total_queries = len(queries)
        report.total_time_ms = sum(q.duration_ms for q in queries)

        # Run analyzers
        analyzers = [NPlusOneAnalyzer(), DuplicateAnalyzer(), MissingIndexAnalyzer()]
        for analyzer in analyzers:
            try:
                prescriptions = analyzer.analyze(queries)
                report.prescriptions.extend(prescriptions)
            except Exception:
                logger.warning(
                    "query_doctor: analyzer %s failed in context manager",
                    analyzer.name,
                    exc_info=True,
                )
    except Exception:
        logger.warning("query_doctor: context manager analysis failed", exc_info=True)
