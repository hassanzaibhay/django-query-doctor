"""Management command to generate QueryTurbo benchmark dashboard.

Generates a standalone HTML report with Chart.js graphs showing cache
performance metrics. The report shows data from the CURRENT process's
cache — if the server is restarted, the cache is empty and the report
shows zeros.

Usage:
    python manage.py query_doctor_report
    python manage.py query_doctor_report --output=report.html
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Generate QueryTurbo benchmark dashboard as a standalone HTML file."""

    help = (
        "Generate a QueryTurbo benchmark dashboard. Shows cache hit/miss rates, "
        "top optimized queries, and Chart.js graphs. Data reflects the current "
        "process cache — the cache resets on server restart. "
        "NOTE: The report contains SQL query templates (without parameter values) "
        "that may reveal database schema information. Do not share the report "
        "publicly if your schema is confidential."
    )

    def add_arguments(self, parser: Any) -> None:
        """Add command arguments."""
        parser.add_argument(
            "--output", "-o",
            default="query_doctor_report.html",
            help="Output file path (default: query_doctor_report.html)",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Execute the command."""
        from query_doctor.reporters.dashboard import DashboardReporter
        from query_doctor.turbo.patch import get_cache
        from query_doctor.turbo.stats import TurboStats

        output_path = options["output"]
        cache = get_cache()

        if cache is None:
            self.stdout.write(
                self.style.WARNING(
                    "QueryTurbo is not active (no cache available). "
                    "Enable TURBO in QUERY_DOCTOR settings to use this command. "
                    "Generating report with empty data."
                )
            )
            stats = {
                "timestamp": 0,
                "total_hits": 0,
                "total_misses": 0,
                "hit_rate": 0,
                "cache_size": 0,
                "max_size": 0,
                "evictions": 0,
                "top_queries": [],
                "prepare_stats": {"prepared_count": 0, "unprepared_count": 0},
            }
        else:
            turbo_stats = TurboStats()
            stats = turbo_stats.snapshot(cache)

        reporter = DashboardReporter()
        path = reporter.generate(stats, output_path)

        self.stdout.write(self.style.SUCCESS(f"Report generated: {path}"))
