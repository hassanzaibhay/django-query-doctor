"""Management command to diagnose all URLs in the Django project.

Crawls the URL configuration, hits each endpoint using Django's test Client,
captures query diagnosis, and generates an app-wise health report.

Usage:
    python manage.py diagnose_project
    python manage.py diagnose_project --output report.html
    python manage.py diagnose_project --apps myapp accounts
    python manage.py diagnose_project --format json
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand

from query_doctor.project_diagnoser import ProjectDiagnoser
from query_doctor.reporters.project_report import (
    ProjectJsonReporter,
    ProjectReportGenerator,
)
from query_doctor.url_discovery import discover_urls


class Command(BaseCommand):
    """Diagnose all URLs in the project and generate an app-wise health report."""

    help = (
        "Diagnose all URLs in the project and generate an app-wise health report "
        "with per-app health scores, query analysis, and prescriptions."
    )

    def add_arguments(self, parser: Any) -> None:
        """Add command arguments."""
        parser.add_argument(
            "--output",
            "-o",
            type=str,
            default="query_doctor_report.html",
            help="Output file path (default: query_doctor_report.html)",
        )
        parser.add_argument(
            "--format",
            type=str,
            choices=["html", "json"],
            default="html",
            help="Report format (default: html)",
        )
        parser.add_argument(
            "--apps",
            nargs="*",
            type=str,
            default=None,
            help="Only diagnose specific apps",
        )
        parser.add_argument(
            "--timeout",
            type=float,
            default=30.0,
            help="Timeout per URL in seconds (default: 30)",
        )
        parser.add_argument(
            "--exclude-urls",
            nargs="*",
            type=str,
            default=["/admin/", "/static/", "/media/", "/__debug__/"],
            help="URL prefixes to exclude",
        )
        parser.add_argument(
            "--methods",
            nargs="*",
            type=str,
            default=["GET"],
            help="HTTP methods to test (default: GET)",
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
        verbosity = options.get("verbosity", 1)
        output_format = options["format"]
        save_baseline = options.get("save_baseline")
        baseline_path = options.get("baseline")
        fail_on_regression = options.get("fail_on_regression", False)
        group_by = options.get("group")

        if verbosity >= 1:
            self.stdout.write("Discovering URLs...")

        urls = discover_urls(
            apps=options["apps"],
            exclude_patterns=options["exclude_urls"],
        )

        if verbosity >= 1:
            self.stdout.write(f"Found {len(urls)} URLs to analyze")

        diagnoser = ProjectDiagnoser(timeout=options["timeout"])

        if verbosity >= 1:
            self.stdout.write("Running diagnosis...")

        result = diagnoser.diagnose(urls, methods=options["methods"])

        # Apply per-file/module filtering to each endpoint's prescriptions
        file_patterns = options.get("file_patterns")
        module_patterns = options.get("module_patterns")
        if file_patterns or module_patterns:
            from query_doctor.filters.file_filter import PrescriptionFilter

            pf = PrescriptionFilter(
                file_patterns=file_patterns,
                module_patterns=module_patterns,
            )
            for app_result in result.app_results:
                for url_result in app_result.url_results:
                    if hasattr(url_result, "report") and url_result.report:
                        url_result.report.prescriptions = pf.filter(
                            url_result.report.prescriptions
                        )

        # Collect all prescriptions across all URLs for baseline/grouping
        all_prescriptions = self._collect_all_prescriptions(result)

        # Save baseline if requested
        if save_baseline:
            self._save_baseline(all_prescriptions, save_baseline)

        # Compare against baseline if requested
        regressions: list[dict[str, Any]] = []
        if baseline_path:
            regressions = self._compare_baseline(all_prescriptions, baseline_path)

        # Grouped output if requested
        if group_by:
            self._render_grouped(all_prescriptions, group_by)

        # Generate and write report
        output_path = options["output"]
        if output_format == "json":
            if output_path.endswith(".html"):
                output_path = output_path.replace(".html", ".json")
            report_content = ProjectJsonReporter().generate(result)
        else:
            report_content = ProjectReportGenerator().generate(result)

        try:
            Path(output_path).write_text(report_content, encoding="utf-8")
        except OSError:
            self.stderr.write(self.style.ERROR(f"Failed to write report to {output_path}"))
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Report saved to {output_path} "
                f"({result.total_urls_analyzed} URLs, "
                f"{result.total_issues} issues, "
                f"health: {result.overall_health_score:.0f}/100)"
            )
        )

        # Fail on regression check
        if fail_on_regression and regressions:
            from django.core.management.base import CommandError

            raise CommandError(f"Found {len(regressions)} regression(s) vs baseline")

    def _collect_all_prescriptions(self, result: Any) -> list[Any]:
        """Collect all prescriptions from all URL results."""
        prescriptions: list[Any] = []
        for app_result in result.app_results:
            for url_result in app_result.url_results:
                if hasattr(url_result, "report") and url_result.report:
                    prescriptions.extend(url_result.report.prescriptions)
        return prescriptions

    def _save_baseline(self, prescriptions: list[Any], path: str) -> None:
        """Save current issues as a baseline snapshot."""
        from query_doctor.baseline import BaselineSnapshot

        issues = self._prescriptions_to_dicts(prescriptions)
        baseline = BaselineSnapshot(issues)
        saved_path = baseline.save(path)
        self.stdout.write(
            self.style.SUCCESS(f"Baseline saved: {saved_path} ({len(issues)} issues)")
        )

    def _compare_baseline(
        self, prescriptions: list[Any], baseline_path: str
    ) -> list[dict[str, Any]]:
        """Compare current issues against a baseline.

        Returns the list of regressions (new issues not in baseline).
        """
        from query_doctor.baseline import BaselineSnapshot

        baseline = BaselineSnapshot.load(baseline_path)
        current = self._prescriptions_to_dicts(prescriptions)
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

    def _render_grouped(self, prescriptions: list[Any], group_by: str) -> None:
        """Render grouped prescriptions to console."""
        from query_doctor.grouping import group_prescriptions

        groups = group_prescriptions(prescriptions, group_by=group_by)
        for group in groups:
            self.stdout.write(f"\n{group.severity.value.upper()}: {group.summary}")
            if group.count > 1:
                for p in group.prescriptions[1:]:
                    self.stdout.write(f"  - {p.description}")

    def _prescriptions_to_dicts(self, prescriptions: list[Any]) -> list[dict[str, Any]]:
        """Convert prescriptions to serializable dicts for baseline."""
        issues: list[dict[str, Any]] = []
        for p in prescriptions:
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
