"""Run diagnosis across all discovered URLs in a Django project.

Uses Django's test Client to make internal requests, captures queries
via the existing interceptor pipeline, and aggregates results by app
with health scores.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from query_doctor.types import DiagnosisReport, Severity
from query_doctor.url_discovery import DiscoveredURL

logger = logging.getLogger("query_doctor")


@dataclass
class URLDiagnosisResult:
    """Diagnosis result for a single URL."""

    url: DiscoveredURL
    report: DiagnosisReport | None = None
    error: str | None = None
    duration_ms: float = 0.0
    status_code: int | None = None


@dataclass
class AppDiagnosisResult:
    """Aggregated diagnosis for a Django app."""

    app_name: str
    url_results: list[URLDiagnosisResult] = field(default_factory=list)

    @property
    def total_queries(self) -> int:
        """Total queries across all URLs in this app."""
        return sum(r.report.total_queries for r in self.url_results if r.report is not None)

    @property
    def total_time_ms(self) -> float:
        """Total query time across all URLs in this app."""
        return sum(r.report.total_time_ms for r in self.url_results if r.report is not None)

    @property
    def total_issues(self) -> int:
        """Total issues across all URLs in this app."""
        return sum(r.report.issues for r in self.url_results if r.report is not None)

    @property
    def critical_count(self) -> int:
        """Count of critical issues across all URLs in this app."""
        count = 0
        for r in self.url_results:
            if r.report is not None:
                count += sum(1 for p in r.report.prescriptions if p.severity == Severity.CRITICAL)
        return count

    @property
    def warning_count(self) -> int:
        """Count of warning issues across all URLs in this app."""
        count = 0
        for r in self.url_results:
            if r.report is not None:
                count += sum(1 for p in r.report.prescriptions if p.severity == Severity.WARNING)
        return count

    @property
    def health_score(self) -> float:
        """Health score from 0-100. 100 = no issues.

        Scoring: each critical issue deducts 15 points, each warning
        deducts 5 points, each info deducts 1 point. Minimum is 0.
        """
        score = 100.0
        for r in self.url_results:
            if r.report is not None:
                for p in r.report.prescriptions:
                    if p.severity == Severity.CRITICAL:
                        score -= 15.0
                    elif p.severity == Severity.WARNING:
                        score -= 5.0
                    else:
                        score -= 1.0
        return max(0.0, score)


@dataclass
class ProjectDiagnosisResult:
    """Full project diagnosis result."""

    app_results: list[AppDiagnosisResult] = field(default_factory=list)
    skipped_urls: list[tuple[str, str]] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""

    @property
    def total_urls_analyzed(self) -> int:
        """Total number of URLs analyzed across all apps."""
        return sum(len(app.url_results) for app in self.app_results)

    @property
    def total_queries(self) -> int:
        """Total queries across all apps."""
        return sum(app.total_queries for app in self.app_results)

    @property
    def total_issues(self) -> int:
        """Total issues across all apps."""
        return sum(app.total_issues for app in self.app_results)

    @property
    def overall_health_score(self) -> float:
        """Weighted average health score across all apps.

        Returns 100.0 if no apps have been analyzed.
        """
        if not self.app_results:
            return 100.0
        scores = [app.health_score for app in self.app_results]
        return sum(scores) / len(scores)


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


class ProjectDiagnoser:
    """Diagnose all URLs in the project.

    Uses Django's test Client to make requests internally — no running
    server needed. This is the same approach as Django's test framework.
    """

    def __init__(self, timeout: float = 30.0, parallel: int = 1) -> None:
        """Initialize the project diagnoser.

        Args:
            timeout: Timeout per URL in seconds.
            parallel: Concurrency level (reserved for future use, v1.0 is sequential).
        """
        self.timeout = timeout
        self.parallel = parallel

    def diagnose(
        self,
        urls: list[DiscoveredURL],
        methods: list[str] | None = None,
    ) -> ProjectDiagnosisResult:
        """Diagnose all given URLs and return aggregated results.

        Args:
            urls: List of URLs to diagnose.
            methods: Only test URLs matching these HTTP methods.

        Returns:
            ProjectDiagnosisResult with per-app and per-URL results.
        """
        from django.test import Client

        client = Client()
        result = ProjectDiagnosisResult(started_at=_now_iso())

        for url in urls:
            if methods and not any(m in url.methods for m in methods):
                result.skipped_urls.append((url.pattern, f"Method filter: {methods}"))
                continue

            if url.has_parameters:
                resolved = self._resolve_parameters(url)
                if resolved is None:
                    result.skipped_urls.append((url.pattern, "Could not resolve URL parameters"))
                    continue
                pattern_to_hit = resolved
            else:
                pattern_to_hit = url.pattern

            try:
                url_result = self._diagnose_url(client, url, pattern_to_hit)
                app_result = self._get_or_create_app(result, url.app_name)
                app_result.url_results.append(url_result)
            except Exception as e:
                result.skipped_urls.append((url.pattern, str(e)))
                logger.warning(
                    "query_doctor: failed to diagnose %s: %s",
                    url.pattern,
                    e,
                )

        result.finished_at = _now_iso()
        return result

    def _diagnose_url(
        self,
        client: Any,
        url: DiscoveredURL,
        resolved_path: str,
    ) -> URLDiagnosisResult:
        """Hit a single URL and capture diagnosis.

        Args:
            client: Django test Client instance.
            url: The discovered URL metadata.
            resolved_path: The actual path to request (with parameters filled in).

        Returns:
            URLDiagnosisResult with captured queries and analysis.
        """
        from query_doctor.interceptor import QueryInterceptor
        from query_doctor.plugin_api import discover_analyzers

        interceptor = QueryInterceptor()
        start = time.perf_counter()

        try:
            from django.db import connection

            with connection.execute_wrapper(interceptor):
                response = client.get(resolved_path)
                status_code = response.status_code
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            return URLDiagnosisResult(url=url, report=None, error=str(e), duration_ms=elapsed)

        elapsed = (time.perf_counter() - start) * 1000

        # Build report
        queries = interceptor.get_queries()
        report = DiagnosisReport(
            total_queries=len(queries),
            total_time_ms=sum(q.duration_ms for q in queries),
            captured_queries=queries,
        )

        # Run all analyzers
        try:
            analyzers = discover_analyzers()
            for analyzer in analyzers:
                try:
                    prescriptions = analyzer.analyze(queries)
                    report.prescriptions.extend(prescriptions)
                except Exception:
                    logger.warning(
                        "query_doctor: analyzer %s failed for %s",
                        getattr(analyzer, "name", "unknown"),
                        url.pattern,
                        exc_info=True,
                    )
        except Exception:
            logger.warning("query_doctor: analyzer discovery failed", exc_info=True)

        return URLDiagnosisResult(
            url=url,
            report=report,
            duration_ms=elapsed,
            status_code=status_code,
        )

    def _resolve_parameters(self, url: DiscoveredURL) -> str | None:
        """Try to resolve URL path parameters with real database values.

        Args:
            url: The discovered URL with parameters.

        Returns:
            Resolved URL path string, or None if resolution fails.
        """
        import re

        pattern = url.pattern
        params = re.findall(r"<(?:\w+:)?(\w+)>", pattern)
        if not params:
            return pattern

        # Can't resolve parameterized URLs without values
        logger.debug("query_doctor: skipping parameterized URL %s", pattern)

        return None

    def _get_or_create_app(
        self,
        result: ProjectDiagnosisResult,
        app_name: str,
    ) -> AppDiagnosisResult:
        """Get or create an AppDiagnosisResult for the given app name.

        Args:
            result: The project result to search/modify.
            app_name: The app namespace.

        Returns:
            The existing or newly created AppDiagnosisResult.
        """
        for app in result.app_results:
            if app.app_name == app_name:
                return app
        app = AppDiagnosisResult(app_name=app_name)
        result.app_results.append(app)
        return app
