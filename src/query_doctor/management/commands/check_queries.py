"""Management command to check for query optimization issues.

Runs the query doctor analysis pipeline against a URL or code block
and outputs results in the specified format. Designed for CI/CD pipelines.

Usage:
    python manage.py check_queries --url /api/books/ --format json
    python manage.py check_queries --format console --fail-on critical
"""

from __future__ import annotations

import contextlib
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.test import RequestFactory

from query_doctor.interceptor import QueryInterceptor
from query_doctor.reporters.json_reporter import JSONReporter
from query_doctor.types import DiagnosisReport, Severity


class Command(BaseCommand):
    """Check for query optimization issues in views."""

    help = (
        "Run query doctor analysis and report optimization issues. "
        "Use --fail-on to set exit code 1 for CI/CD integration."
    )

    def add_arguments(self, parser: Any) -> None:
        """Add command arguments."""
        parser.add_argument(
            "--url",
            default="/",
            help="URL path to analyze (default: /)",
        )
        parser.add_argument(
            "--format",
            choices=["console", "json"],
            default="console",
            help="Output format (default: console)",
        )
        parser.add_argument(
            "--fail-on",
            choices=["critical", "warning", "info"],
            default=None,
            help="Exit with code 1 if issues at this severity or higher are found",
        )
        parser.add_argument(
            "--diff",
            type=str,
            default=None,
            help=(
                "Only report issues in files changed vs this git ref "
                "(e.g., main, origin/develop, abc123)"
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Execute the command."""
        url = options["url"]
        output_format = options["format"]
        fail_on = options["fail_on"]
        diff_ref = options["diff"]

        report = self._run_analysis(url)

        if diff_ref:
            from query_doctor.diff_filter import (
                filter_by_changed_files,
                get_changed_files,
            )

            changed = get_changed_files(diff_ref)
            if not changed:
                self.stdout.write(
                    self.style.WARNING(
                        f"No changed files found vs {diff_ref} (or git not available)"
                    )
                )
            report.prescriptions = filter_by_changed_files(report.prescriptions, changed)

        if output_format == "json":
            reporter = JSONReporter()
            self.stdout.write(reporter.render(report))
        else:
            self._render_console(report)

        if fail_on and self._should_fail(report, fail_on):
            raise CommandError(f"Query doctor found issues at severity '{fail_on}' or higher")

    def _run_analysis(self, url: str) -> DiagnosisReport:
        """Run query analysis for the given URL."""
        from query_doctor.analyzers.duplicate import DuplicateAnalyzer
        from query_doctor.analyzers.missing_index import MissingIndexAnalyzer
        from query_doctor.analyzers.nplusone import NPlusOneAnalyzer

        interceptor = QueryInterceptor()
        report = DiagnosisReport()

        try:
            from django.db import connection

            factory = RequestFactory()
            request = factory.get(url)

            from django.urls import resolve

            with connection.execute_wrapper(interceptor):
                try:
                    match = resolve(url)
                    match.func(request, *match.args, **match.kwargs)
                except Exception:
                    pass
        except Exception:
            pass

        queries = interceptor.get_queries()
        report.captured_queries = queries
        report.total_queries = len(queries)
        report.total_time_ms = sum(q.duration_ms for q in queries)

        analyzers = [NPlusOneAnalyzer(), DuplicateAnalyzer(), MissingIndexAnalyzer()]
        for analyzer in analyzers:
            with contextlib.suppress(Exception):
                report.prescriptions.extend(analyzer.analyze(queries))

        return report

    def _render_console(self, report: DiagnosisReport) -> None:
        """Render report to console output."""
        from query_doctor.reporters.console import ConsoleReporter

        reporter = ConsoleReporter(stream=self.stdout)
        reporter.report(report)

    def _should_fail(self, report: DiagnosisReport, fail_on: str) -> bool:
        """Check if any prescription meets or exceeds the fail-on severity."""
        severity_order = {"info": 0, "warning": 1, "critical": 2}
        fail_level = severity_order.get(fail_on, 0)

        severity_map = {
            Severity.INFO: 0,
            Severity.WARNING: 1,
            Severity.CRITICAL: 2,
        }

        return any(severity_map.get(p.severity, 0) >= fail_level for p in report.prescriptions)
