"""Management command to check DRF serializers for N+1 patterns.

Discovers DRF serializer classes in the project, runs the AST-based
SerializerMethodAnalyzer, and outputs prescriptions using the existing
reporter pipeline.

Usage:
    python manage.py check_serializers
    python manage.py check_serializers --app=myapp
    python manage.py check_serializers --file=myapp/serializers.py
    python manage.py check_serializers --format=json
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Check DRF serializers for SerializerMethodField N+1 patterns."""

    help = (
        "Analyze DRF serializers for SerializerMethodField methods "
        "that may cause N+1 queries. Uses static AST analysis."
    )

    def add_arguments(self, parser: Any) -> None:
        """Add command arguments."""
        parser.add_argument(
            "--app",
            action="append",
            default=None,
            dest="app_labels",
            help=(
                "Only scan serializers in the given app (can be repeated). "
                "Example: --app=myapp --app=otherapp"
            ),
        )
        parser.add_argument(
            "--module",
            action="append",
            default=None,
            dest="module_patterns",
            help=(
                "Only scan the given module path (can be repeated). "
                "Example: --module=myapp.serializers"
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

    def handle(self, *args: Any, **options: Any) -> None:
        """Execute the command."""
        # Check DRF is installed
        try:
            import rest_framework  # noqa: F401
        except ImportError:
            self.stdout.write(
                self.style.WARNING("DRF (djangorestframework) is not installed, skipping.")
            )
            return

        from query_doctor.analyzers.discovery import discover_serializers
        from query_doctor.analyzers.serializer_method import SerializerMethodAnalyzer

        app_labels = options.get("app_labels")
        module_patterns = options.get("module_patterns")
        file_patterns = options.get("file_patterns")
        output_format = options["format"]
        fail_on = options["fail_on"]

        # Discover serializers
        serializers = discover_serializers(
            app_labels=app_labels,
            modules=module_patterns,
        )

        if not serializers:
            self.stdout.write(self.style.WARNING("No serializers found to analyze."))
            return

        self.stdout.write(f"Found {len(serializers)} serializer(s) to analyze...")

        # Run analyzer
        analyzer = SerializerMethodAnalyzer()
        all_prescriptions = []

        for serializer_cls in serializers:
            try:
                prescriptions = analyzer.analyze(serializer_cls)
                all_prescriptions.extend(prescriptions)
            except Exception as e:
                self.stderr.write(
                    self.style.WARNING(
                        f"Error analyzing {serializer_cls.__name__}: {e}"
                    )
                )

        # Apply per-file filtering
        if file_patterns:
            from query_doctor.filters.file_filter import PrescriptionFilter

            pf = PrescriptionFilter(file_patterns=file_patterns)
            all_prescriptions = pf.filter(all_prescriptions)

        # Build a report
        from query_doctor.types import DiagnosisReport

        report = DiagnosisReport(prescriptions=all_prescriptions)

        # Output
        if output_format == "json":
            from query_doctor.reporters.json_reporter import JSONReporter

            reporter = JSONReporter()
            self.stdout.write(reporter.render(report))
        else:
            self._render_console(report)

        # Summary
        if all_prescriptions:
            self.stdout.write(
                self.style.WARNING(
                    f"\nFound {len(all_prescriptions)} potential N+1 issue(s) "
                    f"in SerializerMethodField methods."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS("\nNo SerializerMethodField N+1 issues found.")
            )

        # Fail-on check
        if fail_on and self._should_fail(report, fail_on):
            from django.core.management.base import CommandError

            raise CommandError(
                f"check_serializers found issues at severity '{fail_on}' or higher"
            )

    def _render_console(self, report: Any) -> None:
        """Render report to console output."""
        from query_doctor.reporters.console import ConsoleReporter

        reporter = ConsoleReporter(stream=self.stdout)
        reporter.report(report)

    def _should_fail(self, report: Any, fail_on: str) -> bool:
        """Check if any prescription meets or exceeds the fail-on severity."""
        from query_doctor.types import Severity

        severity_order = {"info": 0, "warning": 1, "critical": 2}
        fail_level = severity_order.get(fail_on, 0)

        severity_map = {
            Severity.INFO: 0,
            Severity.WARNING: 1,
            Severity.CRITICAL: 2,
        }

        return any(
            severity_map.get(p.severity, 0) >= fail_level
            for p in report.prescriptions
        )
