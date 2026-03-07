"""Django middleware that activates query diagnosis per request.

Installs a query interceptor via connection.execute_wrapper(), captures
all SQL queries during the request, runs enabled analyzers, and sends
the diagnosis report to enabled reporters.
"""

from __future__ import annotations

import logging
import random
from collections.abc import Callable
from typing import Any

from django.http import HttpRequest, HttpResponse

from query_doctor.analyzers.duplicate import DuplicateAnalyzer
from query_doctor.analyzers.nplusone import NPlusOneAnalyzer
from query_doctor.conf import get_config
from query_doctor.interceptor import QueryInterceptor
from query_doctor.reporters.console import ConsoleReporter
from query_doctor.types import DiagnosisReport

logger = logging.getLogger("query_doctor")


def _get_enabled_analyzers(config: dict[str, Any]) -> list[Any]:
    """Return a list of enabled analyzer instances."""
    analyzers: list[Any] = []
    analyzer_config = config.get("ANALYZERS", {})

    if analyzer_config.get("nplusone", {}).get("enabled", True):
        analyzers.append(NPlusOneAnalyzer())
    if analyzer_config.get("duplicate", {}).get("enabled", True):
        analyzers.append(DuplicateAnalyzer())

    return analyzers


def _get_reporters(config: dict[str, Any]) -> list[Any]:
    """Return a list of enabled reporter instances."""
    reporters: list[Any] = []
    reporter_names = config.get("REPORTERS", ["console"])

    if "console" in reporter_names:
        reporters.append(ConsoleReporter())

    return reporters


class QueryDoctorMiddleware:
    """Django middleware that activates query diagnosis per request.

    Installs an execute_wrapper on the database connection to capture
    all SQL queries. After the response is generated, runs all enabled
    analyzers and sends reports to configured reporters.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        """Initialize the middleware.

        Args:
            get_response: The next middleware or view in the chain.
        """
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Process a request through the query doctor pipeline.

        Args:
            request: The incoming HTTP request.

        Returns:
            The HTTP response from the view.
        """
        try:
            config = get_config()
        except Exception:
            logger.warning("query_doctor: failed to load config", exc_info=True)
            return self.get_response(request)

        # Check if enabled
        if not config.get("ENABLED", True):
            return self.get_response(request)

        # Check sampling rate
        sample_rate = config.get("SAMPLE_RATE", 1.0)
        if sample_rate < 1.0 and random.random() > sample_rate:
            return self.get_response(request)

        # Check URL against ignore list
        ignore_urls = config.get("IGNORE_URLS", [])
        if any(request.path.startswith(url) for url in ignore_urls):
            return self.get_response(request)

        # Install interceptor and process request
        interceptor = QueryInterceptor(capture_stack=config.get("CAPTURE_STACK_TRACES", True))

        from django.db import connection

        with connection.execute_wrapper(interceptor):
            response = self.get_response(request)

        # Run analysis (never crash the host app)
        try:
            self._analyze_and_report(interceptor, config)
        except Exception:
            logger.warning("query_doctor: analysis failed", exc_info=True)

        return response

    def _analyze_and_report(self, interceptor: QueryInterceptor, config: dict[str, Any]) -> None:
        """Run analyzers and send report to reporters."""
        queries = interceptor.get_queries()
        if not queries:
            return

        report = DiagnosisReport(
            total_queries=len(queries),
            total_time_ms=sum(q.duration_ms for q in queries),
            captured_queries=queries,
        )

        # Run all enabled analyzers
        analyzers = _get_enabled_analyzers(config)
        for analyzer in analyzers:
            try:
                prescriptions = analyzer.analyze(queries)
                report.prescriptions.extend(prescriptions)
            except Exception:
                logger.warning(
                    "query_doctor: analyzer %s failed",
                    getattr(analyzer, "name", "unknown"),
                    exc_info=True,
                )

        # Only report if there are issues
        if report.prescriptions:
            reporters = _get_reporters(config)
            for reporter in reporters:
                try:
                    reporter.report(report)
                except Exception:
                    logger.warning("query_doctor: reporter failed", exc_info=True)
