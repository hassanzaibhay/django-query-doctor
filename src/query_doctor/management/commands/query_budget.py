"""Management command to enforce query budgets.

Executes a Python code block and checks that the number of queries
stays within the specified budget. Designed for CI/CD pipelines.

Usage:
    python manage.py query_budget --max-queries 20
    python manage.py query_budget --max-queries 20 --execute "..."
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from query_doctor.interceptor import QueryInterceptor
from query_doctor.types import DiagnosisReport


class Command(BaseCommand):
    """Enforce query budgets for views and code blocks."""

    help = (
        "Run a code block and enforce a maximum query count. "
        "Exits with code 1 if the budget is exceeded."
    )

    def add_arguments(self, parser: Any) -> None:
        """Add command arguments."""
        parser.add_argument(
            "--max-queries",
            type=int,
            required=True,
            help="Maximum number of queries allowed",
        )
        parser.add_argument(
            "--max-time-ms",
            type=float,
            default=None,
            help="Maximum total query time in milliseconds",
        )
        parser.add_argument(
            "--execute",
            default=None,
            help="Python code to execute and measure",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Execute the command."""
        max_queries = options["max_queries"]
        max_time_ms = options["max_time_ms"]
        execute_code = options["execute"]

        report = self._run_with_budget(execute_code)

        self.stdout.write(
            f"Query budget: {report.total_queries} queries, "
            f"{report.total_time_ms:.1f}ms "
            f"(limit: {max_queries} queries"
            + (f", {max_time_ms:.1f}ms" if max_time_ms else "")
            + ")"
        )

        if report.total_queries > max_queries:
            raise CommandError(
                f"Query budget exceeded: {report.total_queries} queries (max: {max_queries})"
            )

        if max_time_ms and report.total_time_ms > max_time_ms:
            raise CommandError(
                f"Query time budget exceeded: {report.total_time_ms:.1f}ms "
                f"(max: {max_time_ms:.1f}ms)"
            )

        self.stdout.write(self.style.SUCCESS("Query budget OK"))

    def _run_with_budget(self, execute_code: str | None) -> DiagnosisReport:
        """Run code and capture query metrics."""
        interceptor = QueryInterceptor()

        from django.db import connection

        with connection.execute_wrapper(interceptor):
            if execute_code:
                exec(execute_code)

        queries = interceptor.get_queries()
        return DiagnosisReport(
            total_queries=len(queries),
            total_time_ms=sum(q.duration_ms for q in queries),
            captured_queries=queries,
        )
