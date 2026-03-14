"""Management command to auto-fix diagnosed query issues.

Runs the diagnosis pipeline, generates proposed fixes, and either
displays a diff (--dry-run, default) or applies changes to disk (--apply).

Usage:
    python manage.py fix_queries --dry-run
    python manage.py fix_queries --apply
    python manage.py fix_queries --issue-type n_plus_one --file myapp/views.py
"""

from __future__ import annotations

import contextlib
from typing import Any

from django.core.management.base import BaseCommand

from query_doctor.fixer import ProposedFix, QueryFixer
from query_doctor.interceptor import QueryInterceptor
from query_doctor.types import DiagnosisReport


class Command(BaseCommand):
    """Auto-fix diagnosed query issues."""

    help = (
        "Auto-fix diagnosed query optimization issues. "
        "Defaults to --dry-run which shows a diff without modifying files."
    )

    def add_arguments(self, parser: Any) -> None:
        """Add command arguments."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=True,
            help="Show diff without applying (default)",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply fixes to source files",
        )
        parser.add_argument(
            "--issue-type",
            type=str,
            nargs="*",
            help="Only fix specific issue types (e.g., n_plus_one duplicate)",
        )
        parser.add_argument(
            "--file",
            type=str,
            nargs="*",
            help="Only fix specific files",
        )
        parser.add_argument(
            "--no-backup",
            action="store_true",
            help="Do not create .bak files when applying",
        )
        parser.add_argument(
            "--url",
            default="/",
            help="URL path to analyze (default: /)",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Execute the command."""
        apply_mode = options["apply"]
        issue_types = options.get("issue_type")
        file_filter = options.get("file")
        no_backup = options.get("no_backup", False)

        # Get all fixes
        fixes = self._get_fixes(options)

        # Apply filters
        if issue_types:
            fixes = [f for f in fixes if f.prescription.issue_type.value in issue_types]

        if file_filter:
            fixes = [
                f
                for f in fixes
                if any(f.file_path.endswith(fp) or fp.endswith(f.file_path) for fp in file_filter)
            ]

        if not fixes:
            self.stdout.write(self.style.SUCCESS("No fixes to apply."))
            return

        fixer = QueryFixer()
        diff = fixer.generate_diff(fixes)

        if apply_mode:
            self.stdout.write(diff)
            modified = fixer.apply_fixes(fixes, backup=not no_backup)
            self.stdout.write(
                self.style.SUCCESS(f"Applied {len(fixes)} fix(es) to {len(modified)} file(s).")
            )
            if not no_backup:
                self.stdout.write("Backup files created (.bak)")
        else:
            self.stdout.write("Dry run — showing proposed changes:\n")
            self.stdout.write(diff)
            self.stdout.write(
                self.style.WARNING(
                    f"\n{len(fixes)} fix(es) available. Run with --apply to write changes."
                )
            )

    def _get_fixes(self, options: dict[str, Any]) -> list[ProposedFix]:
        """Run diagnosis and generate fixes.

        Args:
            options: Command options dict.

        Returns:
            List of proposed fixes.
        """
        report = self._run_analysis(options.get("url", "/"))

        # Apply .queryignore filtering
        try:
            from query_doctor.ignore import filter_prescriptions, load_queryignore

            rules = load_queryignore()
            if rules:
                report.prescriptions = filter_prescriptions(report.prescriptions, rules)
        except Exception:
            pass

        fixer = QueryFixer()
        return fixer.generate_fixes(report.prescriptions)

    def _run_analysis(self, url: str) -> DiagnosisReport:
        """Run query analysis for the given URL."""
        from query_doctor.plugin_api import discover_analyzers

        interceptor = QueryInterceptor()
        report = DiagnosisReport()

        try:
            from django.db import connection
            from django.test import RequestFactory

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

        analyzers = discover_analyzers()
        for analyzer in analyzers:
            with contextlib.suppress(Exception):
                if analyzer.is_enabled():
                    report.prescriptions.extend(analyzer.analyze(queries))

        return report
