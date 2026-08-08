"""Context managers for targeted query diagnosis.

Provides diagnose_queries() for diagnosing queries within a specific
code block rather than an entire request.
"""

from __future__ import annotations

import asyncio
import logging
import warnings
from collections.abc import Generator
from contextlib import contextmanager

from query_doctor.exceptions import QueryDoctorWarning
from query_doctor.interceptor import build_interceptor
from query_doctor.pipeline import analyze as pipeline_analyze
from query_doctor.types import DiagnosisReport

logger = logging.getLogger("query_doctor")


def _warn_if_entered_on_an_event_loop() -> None:
    """Warn when this block cannot capture, instead of reporting zero silently.

    ``diagnose_queries()`` installs its execute_wrapper on the calling thread's
    connection object, and Django's connection registry is thread-local. Entered
    from a coroutine, the wrapper therefore lands on the event loop thread's
    connection while the ORM runs in the thread-sensitive executor holding a
    different one, and the block reports zero queries however many it issued.

    The predicate is "a loop is running on *this* thread", which is exactly the
    broken case. A sync view served under ASGI and a sync_to_async-wrapped
    helper both run in the executor thread, have no running loop, and capture
    correctly -- so neither warns.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:  # no loop on this thread: capture works normally
        return

    warnings.warn(
        "query_doctor: diagnose_queries() was entered from a coroutine and will "
        "capture nothing. It installs its execute_wrapper on this thread's database "
        "connection, but Django routes ORM work in async code to a separate executor "
        "thread holding a different connection. Use the query_doctor middleware to "
        "diagnose async views, or call diagnose_queries() from synchronous code.",
        QueryDoctorWarning,
        stacklevel=4,
    )


@contextmanager
def diagnose_queries() -> Generator[DiagnosisReport, None, None]:
    """Context manager for targeted query diagnosis.

    Captures and analyzes all SQL queries executed within the context.
    The DiagnosisReport is yielded and populated after the context exits.

    Synchronous only. Entering the block from a coroutine emits a
    ``QueryDoctorWarning`` and captures nothing -- use the middleware for
    async views. See ``docs/guides/async-support.md``.

    Usage:
        with diagnose_queries() as report:
            # ... your ORM code here ...
        print(report.issues)
    """
    _warn_if_entered_on_an_event_loop()

    report = DiagnosisReport()
    interceptor = build_interceptor()

    from django.db import connection

    try:
        with connection.execute_wrapper(interceptor):
            yield report

        # After context exits, run analysis
        try:
            queries = interceptor.get_queries()
            report.captured_queries = queries
            report.total_queries = len(queries)
            report.total_time_ms = sum(q.duration_ms for q in queries)

            # Run analyzers and apply .queryignore filtering via the shared pipeline.
            report.prescriptions = pipeline_analyze(queries, source="context_manager")
        except Exception:
            logger.warning("query_doctor: context manager analysis failed", exc_info=True)
    finally:
        # The report keeps the queries; the context must not keep a second
        # reference to them once the block is done with.
        interceptor.release()
