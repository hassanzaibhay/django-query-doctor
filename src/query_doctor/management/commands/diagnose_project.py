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

    def handle(self, *args: Any, **options: Any) -> None:
        """Execute the command."""
        verbosity = options.get("verbosity", 1)
        output_format = options["format"]

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
