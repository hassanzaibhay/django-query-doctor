"""Django middleware that activates query diagnosis per request.

Installs a query interceptor via connection.execute_wrapper(), captures
all SQL queries during the request, runs enabled analyzers, and sends
the diagnosis report to enabled reporters.

Supports both sync and async Django views (Django 4.1+).
"""

from __future__ import annotations

import inspect
import logging
import random
from collections.abc import Callable
from typing import Any

from django.http import HttpRequest

from query_doctor.analyzers.duplicate import DuplicateAnalyzer
from query_doctor.analyzers.missing_index import MissingIndexAnalyzer
from query_doctor.analyzers.nplusone import NPlusOneAnalyzer
from query_doctor.conf import get_config
from query_doctor.interceptor import QueryInterceptor
from query_doctor.reporters.console import ConsoleReporter
from query_doctor.reporters.json_reporter import JSONReporter
from query_doctor.reporters.log_reporter import LogReporter
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
    if analyzer_config.get("missing_index", {}).get("enabled", True):
        analyzers.append(MissingIndexAnalyzer())

    return analyzers


def _get_reporters(config: dict[str, Any]) -> list[Any]:
    """Return a list of enabled reporter instances."""
    reporters: list[Any] = []
    reporter_names = config.get("REPORTERS", ["console"])

    if "console" in reporter_names:
        reporters.append(ConsoleReporter())
    if "json" in reporter_names:
        json_path = config.get("JSON_REPORT_PATH")
        reporters.append(JSONReporter(output_path=json_path))
    if "log" in reporter_names:
        reporters.append(LogReporter())

    return reporters


class QueryDoctorMiddleware:
    """Django middleware that activates query diagnosis per request.

    Installs an execute_wrapper on the database connection to capture
    all SQL queries. After the response is generated, runs all enabled
    analyzers and sends reports to configured reporters.

    Supports both sync and async views via sync_capable and async_capable.
    """

    sync_capable = True
    async_capable = True

    def __init__(self, get_response: Callable[..., Any]) -> None:
        """Initialize the middleware.

        Args:
            get_response: The next middleware or view in the chain.
        """
        self.get_response = get_response
        self._is_async = inspect.iscoroutinefunction(get_response)

    def __call__(self, request: HttpRequest) -> Any:
        """Process a request through the query doctor pipeline.

        Routes to sync or async path based on the get_response type.

        Args:
            request: The incoming HTTP request.

        Returns:
            The HTTP response from the view.
        """
        if self._is_async:
            return self.__acall__(request)
        return self._sync_call(request)

    async def __acall__(self, request: HttpRequest) -> Any:
        """Process an async request through the query doctor pipeline.

        Args:
            request: The incoming HTTP request.

        Returns:
            The HTTP response from the async view.
        """
        try:
            config = get_config()
        except Exception:
            logger.warning("query_doctor: failed to load config", exc_info=True)
            return await self.get_response(request)

        if not self._should_process(request, config):
            return await self.get_response(request)

        interceptor = QueryInterceptor(capture_stack=config.get("CAPTURE_STACK_TRACES", True))

        from django.db import connection

        with connection.execute_wrapper(interceptor):
            response = await self.get_response(request)

        try:
            self._analyze_and_report(interceptor, config, request)
        except Exception:
            logger.warning("query_doctor: analysis failed", exc_info=True)

        return response

    def _sync_call(self, request: HttpRequest) -> Any:
        """Process a sync request through the query doctor pipeline.

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

        if not self._should_process(request, config):
            return self.get_response(request)

        interceptor = QueryInterceptor(capture_stack=config.get("CAPTURE_STACK_TRACES", True))

        from django.db import connection

        with connection.execute_wrapper(interceptor):
            response = self.get_response(request)

        try:
            self._analyze_and_report(interceptor, config, request)
        except Exception:
            logger.warning("query_doctor: analysis failed", exc_info=True)

        return response

    def _should_process(self, request: HttpRequest, config: dict[str, Any]) -> bool:
        """Check if this request should be processed.

        Args:
            request: The incoming HTTP request.
            config: The query doctor configuration.

        Returns:
            True if the request should be processed, False otherwise.
        """
        if not config.get("ENABLED", True):
            return False

        sample_rate = config.get("SAMPLE_RATE", 1.0)
        if sample_rate < 1.0 and random.random() > sample_rate:
            return False

        ignore_urls = config.get("IGNORE_URLS", [])
        return not any(request.path.startswith(url) for url in ignore_urls)

    def _analyze_and_report(
        self,
        interceptor: QueryInterceptor,
        config: dict[str, Any],
        request: HttpRequest | None = None,
    ) -> None:
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

        # Apply .queryignore filtering
        try:
            from query_doctor.ignore import filter_prescriptions, load_queryignore

            rules = load_queryignore()
            if rules:
                report.prescriptions = filter_prescriptions(report.prescriptions, rules)
        except Exception:
            logger.warning("query_doctor: queryignore filtering failed", exc_info=True)

        # Record for admin dashboard if enabled
        dashboard_config = config.get("ADMIN_DASHBOARD", {})
        if dashboard_config.get("enabled", False) and request is not None:
            try:
                from query_doctor.admin_panel import record_report

                record_report(request.path, request.method or "GET", report)
            except Exception:
                logger.warning(
                    "query_doctor: admin dashboard recording failed",
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
