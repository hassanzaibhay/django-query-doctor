"""Management command to check for query optimization issues.

Runs the query doctor analysis pipeline against a URL or code block
and outputs results in the specified format. Designed for CI/CD pipelines.

Usage:
    python manage.py check_queries --url /api/books/ --format json
    python manage.py check_queries --format console --fail-on critical
    python manage.py check_queries --save-baseline=.query-baseline.json
    python manage.py check_queries --baseline=.query-baseline.json --fail-on-regression
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
        parser.add_argument(
            "--file",
            action="append",
            default=None,
            dest="file_patterns",
            help=(
                "Only report issues in the given file (substring match). "
                "Can be specified multiple times."
            ),
        )
        parser.add_argument(
            "--module",
            action="append",
            default=None,
            dest="module_patterns",
            help=(
                "Only report issues in the given module (substring match). "
                "Can be specified multiple times."
            ),
        )
        parser.add_argument(
            "--output",
            "-o",
            type=str,
            default=None,
            help="Write output to a file instead of stdout",
        )
        parser.add_argument(
            "--save-baseline",
            type=str,
            default=None,
            help="Save current issues as a baseline snapshot (JSON file)",
        )
        parser.add_argument(
            "--baseline",
            type=str,
            default=None,
            help="Compare against a baseline snapshot, show only regressions",
        )
        parser.add_argument(
            "--fail-on-regression",
            action="store_true",
            default=False,
            help="Exit with code 1 if new issues found vs baseline",
        )
        parser.add_argument(
            "--group",
            nargs="?",
            const="file_analyzer",
            default=None,
            choices=["file_analyzer", "root_cause", "view"],
            help="Group related prescriptions (default strategy: file_analyzer)",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Execute the command."""
        url = options["url"]
        output_format = options["format"]
        fail_on = options["fail_on"]
        diff_ref = options["diff"]
        file_patterns = options.get("file_patterns")
        module_patterns = options.get("module_patterns")
        output_path = options.get("output")
        save_baseline = options.get("save_baseline")
        baseline_path = options.get("baseline")
        fail_on_regression = options.get("fail_on_regression", False)
        group_by = options.get("group")

        report = self._run_analysis(url)

        # Apply per-file/module filtering
        if file_patterns or module_patterns:
            from query_doctor.filters.file_filter import PrescriptionFilter

            pf = PrescriptionFilter(
                file_patterns=file_patterns,
                module_patterns=module_patterns,
            )
            report.prescriptions = pf.filter(report.prescriptions)

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

        # Save baseline if requested
        if save_baseline:
            self._save_baseline(report, save_baseline)

        # Compare against baseline if requested
        regressions: list[Any] = []
        if baseline_path:
            regressions = self._compare_baseline(report, baseline_path)

        # Group prescriptions if requested
        if group_by:
            self._render_grouped(report, group_by)
        elif output_format == "json":
            output_text = JSONReporter().render(report)
            if output_path:
                self._write_output(output_text, output_path)
            else:
                self.stdout.write(output_text)
        else:
            self._render_console(report)

        # Fail checks
        if fail_on_regression and regressions:
            raise CommandError(f"Found {len(regressions)} regression(s) vs baseline")

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

    def _render_grouped(self, report: DiagnosisReport, group_by: str) -> None:
        """Render grouped prescriptions to console."""
        from query_doctor.grouping import group_prescriptions

        groups = group_prescriptions(report.prescriptions, group_by=group_by)
        for group in groups:
            self.stdout.write(f"\n{group.severity.value.upper()}: {group.summary}")
            if group.count > 1:
                for p in group.prescriptions[1:]:
                    self.stdout.write(f"  - {p.description}")

    def _save_baseline(self, report: DiagnosisReport, path: str) -> None:
        """Save current issues as a baseline snapshot."""
        from query_doctor.baseline import BaselineSnapshot

        issues = self._prescriptions_to_dicts(report)
        baseline = BaselineSnapshot(issues)
        saved_path = baseline.save(path)
        self.stdout.write(
            self.style.SUCCESS(f"Baseline saved: {saved_path} ({len(issues)} issues)")
        )

    def _compare_baseline(
        self, report: DiagnosisReport, baseline_path: str
    ) -> list[dict[str, Any]]:
        """Compare current issues against a baseline.

        Returns the list of regressions (new issues not in baseline).
        """
        from query_doctor.baseline import BaselineSnapshot

        baseline = BaselineSnapshot.load(baseline_path)
        current = self._prescriptions_to_dicts(report)
        regressions = baseline.find_regressions(current)
        resolved = baseline.find_resolved(current)

        if resolved:
            self.stdout.write(
                self.style.SUCCESS(f"Resolved since baseline: {len(resolved)} issue(s)")
            )
        if regressions:
            self.stdout.write(self.style.WARNING(f"New regressions: {len(regressions)} issue(s)"))
            for r in regressions:
                self.stdout.write(f"  - {r.get('message', r.get('description', ''))}")
        elif not resolved:
            self.stdout.write("No changes from baseline.")

        return regressions

    def _prescriptions_to_dicts(self, report: DiagnosisReport) -> list[dict[str, Any]]:
        """Convert prescriptions to serializable dicts for baseline."""
        issues: list[dict[str, Any]] = []
        for p in report.prescriptions:
            issues.append(
                {
                    "issue_type": p.issue_type.value,
                    "severity": p.severity.value,
                    "description": p.description,
                    "file_path": p.callsite.filepath if p.callsite else "",
                    "line": p.callsite.line_number if p.callsite else 0,
                    "fix_suggestion": p.fix_suggestion,
                }
            )
        return issues

    def _write_output(self, content: str, path: str) -> None:
        """Write content to a file."""
        from pathlib import Path

        Path(path).write_text(content, encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Output written to {path}"))

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
