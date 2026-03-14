"""
Copy this into your test suite to start catching query regressions.
"""

import pytest
from django.test import Client
from query_doctor import diagnose_queries


class TestQueryPerformance:
    """Query performance regression tests."""

    def test_homepage_no_nplusone(self):
        """Homepage should not have N+1 queries."""
        client = Client()
        with diagnose_queries() as report:
            client.get("/")

        assert not report.has_critical, (
            f"Critical query issues on homepage: "
            f"{[rx.description for rx in report.prescriptions if rx.severity.value == 'critical']}"
        )

    def test_api_books_query_budget(self):
        """API books endpoint should stay under 10 queries."""
        client = Client()
        with diagnose_queries() as report:
            client.get("/api/books/")

        assert report.total_queries <= 10, (
            f"Too many queries: {report.total_queries}. "
            f"Issues: {[rx.description for rx in report.prescriptions]}"
        )

    def test_no_duplicate_queries(self):
        """No duplicate queries on the dashboard."""
        client = Client()
        with diagnose_queries() as report:
            client.get("/dashboard/")

        duplicates = [
            rx for rx in report.prescriptions
            if rx.issue_type.value == "duplicate_query"
        ]
        assert len(duplicates) == 0, (
            f"Found {len(duplicates)} duplicate queries: "
            f"{[rx.description for rx in duplicates]}"
        )
