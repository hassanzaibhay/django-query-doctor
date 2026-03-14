"""Tests for context managers in query_doctor.context_managers."""

from __future__ import annotations

import pytest

from query_doctor.context_managers import diagnose_queries
from query_doctor.types import IssueType
from tests.factories import BookFactory


@pytest.mark.django_db
class TestDiagnoseQueries:
    """Tests for diagnose_queries() context manager."""

    def test_captures_queries(self) -> None:
        """Should capture queries executed within the context."""
        BookFactory()

        with diagnose_queries() as report:
            from tests.testapp.models import Book

            list(Book.objects.all())

        assert report.total_queries >= 1
        assert len(report.captured_queries) >= 1

    def test_reports_total_time(self) -> None:
        """Should report total query time."""
        BookFactory()

        with diagnose_queries() as report:
            from tests.testapp.models import Book

            list(Book.objects.all())

        assert report.total_time_ms >= 0

    def test_detects_nplusone(self) -> None:
        """Should detect N+1 queries within the context."""
        for _ in range(5):
            BookFactory()

        with diagnose_queries() as report:
            from tests.testapp.models import Book

            for book in Book.objects.all():
                _ = book.author.name

        assert report.issues >= 1
        assert any(p.issue_type == IssueType.N_PLUS_ONE for p in report.prescriptions)

    def test_clean_context_no_queries(self) -> None:
        """No queries in context should produce empty report."""
        with diagnose_queries() as report:
            pass  # No queries

        assert report.total_queries == 0
        assert report.issues == 0

    def test_report_available_after_context(self) -> None:
        """Report should be fully populated after context exits."""
        BookFactory()

        with diagnose_queries() as report:
            from tests.testapp.models import Book

            list(Book.objects.all())

        # Report should be usable after the context
        assert isinstance(report.total_queries, int)
        assert isinstance(report.total_time_ms, float)
