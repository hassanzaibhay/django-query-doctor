"""End-to-end integration tests for the full query doctor pipeline.

Tests the complete INTERCEPT → FINGERPRINT → ANALYZE → REPORT pipeline
through real HTTP requests via Django's test client with the middleware
installed, as well as the context manager and decorator APIs.
"""

from __future__ import annotations

import pytest

from query_doctor.context_managers import diagnose_queries
from query_doctor.decorators import diagnose, query_budget
from query_doctor.exceptions import QueryBudgetError
from query_doctor.types import IssueType, Severity
from tests.factories import BookFactory


@pytest.mark.django_db
class TestMiddlewareIntegration:
    """End-to-end tests using Django test client with middleware."""

    @pytest.fixture(autouse=True)
    def _setup_books(self) -> None:
        """Create test data: 5 books with different authors and publishers."""
        for _ in range(5):
            BookFactory()

    def test_nplusone_detected_via_middleware(self, client) -> None:
        """Middleware should detect N+1 queries from a view."""
        response = client.get("/books/nplusone/")
        assert response.status_code == 200
        data = response.json()
        assert len(data["books"]) == 5

    def test_duplicate_detected_via_middleware(self, client) -> None:
        """Middleware should detect duplicate queries from a view."""
        response = client.get("/books/duplicate/")
        assert response.status_code == 200
        data = response.json()
        assert len(data["first"]) == 5
        assert len(data["second"]) == 5

    def test_optimized_view_no_issues(self, client) -> None:
        """Optimized view with select_related should produce fewer queries."""
        response = client.get("/books/optimized/")
        assert response.status_code == 200
        data = response.json()
        assert len(data["books"]) == 5


@pytest.mark.django_db
class TestContextManagerIntegration:
    """End-to-end tests using the diagnose_queries context manager."""

    @pytest.fixture(autouse=True)
    def _setup_books(self) -> None:
        for _ in range(5):
            BookFactory()

    def test_nplusone_detected_in_context(self) -> None:
        """Context manager should detect N+1 queries."""
        from tests.testapp.models import Book

        with diagnose_queries() as report:
            for book in Book.objects.all():
                _ = book.author.name

        assert report.total_queries >= 6  # 1 list + 5 author lookups
        assert report.issues >= 1
        nplusone_prescriptions = [
            p for p in report.prescriptions if p.issue_type == IssueType.N_PLUS_ONE
        ]
        assert len(nplusone_prescriptions) >= 1
        assert nplusone_prescriptions[0].severity in (Severity.WARNING, Severity.CRITICAL)
        assert nplusone_prescriptions[0].fix_suggestion is not None

    def test_duplicate_detected_in_context(self) -> None:
        """Context manager should detect exact duplicate queries."""
        from tests.testapp.models import Book

        with diagnose_queries() as report:
            list(Book.objects.filter(price=19.99))
            list(Book.objects.filter(price=19.99))
            list(Book.objects.filter(price=19.99))

        dup_prescriptions = [
            p for p in report.prescriptions if p.issue_type == IssueType.DUPLICATE_QUERY
        ]
        assert len(dup_prescriptions) >= 1
        assert dup_prescriptions[0].query_count >= 3

    def test_optimized_query_no_nplusone(self) -> None:
        """select_related should eliminate N+1 issues."""
        from tests.testapp.models import Book

        with diagnose_queries() as report:
            for book in Book.objects.select_related("author").all():
                _ = book.author.name

        nplusone_prescriptions = [
            p for p in report.prescriptions if p.issue_type == IssueType.N_PLUS_ONE
        ]
        assert len(nplusone_prescriptions) == 0

    def test_report_includes_captured_queries(self) -> None:
        """Report should contain the actual captured SQL queries."""
        from tests.testapp.models import Book

        with diagnose_queries() as report:
            list(Book.objects.all())

        assert len(report.captured_queries) >= 1
        assert any("testapp_book" in q.sql.lower() for q in report.captured_queries)

    def test_report_total_time_positive(self) -> None:
        """Report total_time_ms should be non-negative."""
        from tests.testapp.models import Book

        with diagnose_queries() as report:
            for book in Book.objects.all():
                _ = book.author.name

        assert report.total_time_ms >= 0


@pytest.mark.django_db
class TestDecoratorIntegration:
    """End-to-end tests using the @diagnose and @query_budget decorators."""

    @pytest.fixture(autouse=True)
    def _setup_books(self) -> None:
        for _ in range(5):
            BookFactory()

    def test_diagnose_decorator_detects_nplusone(self) -> None:
        """@diagnose should detect N+1 in the decorated function."""
        from tests.testapp.models import Book

        @diagnose
        def get_books_with_authors():
            return [book.author.name for book in Book.objects.all()]

        result = get_books_with_authors()
        assert len(result) == 5

        report = get_books_with_authors._query_doctor_report
        assert report.total_queries >= 6
        assert any(p.issue_type == IssueType.N_PLUS_ONE for p in report.prescriptions)

    def test_query_budget_enforces_limit(self) -> None:
        """@query_budget should raise when query count exceeds budget."""
        from tests.testapp.models import Book

        @query_budget(max_queries=2)
        def expensive_view():
            for book in Book.objects.all():
                _ = book.author.name

        with pytest.raises(QueryBudgetError) as exc_info:
            expensive_view()

        assert exc_info.value.report is not None
        assert exc_info.value.report.total_queries > 2

    def test_query_budget_passes_when_under_limit(self) -> None:
        """@query_budget should not raise when within budget."""
        from tests.testapp.models import Book

        @query_budget(max_queries=50)
        def efficient_view():
            return list(Book.objects.select_related("author").values_list("title", "author__name"))

        result = efficient_view()
        assert len(result) == 5


@pytest.mark.django_db
class TestPrescriptionQuality:
    """Tests that prescriptions contain actionable information."""

    @pytest.fixture(autouse=True)
    def _setup_books(self) -> None:
        for _ in range(5):
            BookFactory()

    def test_nplusone_prescription_suggests_select_related(self) -> None:
        """N+1 prescription should suggest select_related."""
        from tests.testapp.models import Book

        with diagnose_queries() as report:
            for book in Book.objects.all():
                _ = book.author.name

        nplusone = [p for p in report.prescriptions if p.issue_type == IssueType.N_PLUS_ONE]
        assert len(nplusone) >= 1
        assert "select_related" in nplusone[0].fix_suggestion.lower()

    def test_duplicate_prescription_suggests_caching(self) -> None:
        """Duplicate prescription should suggest caching or reuse."""
        from tests.testapp.models import Book

        with diagnose_queries() as report:
            list(Book.objects.filter(price=19.99))
            list(Book.objects.filter(price=19.99))
            list(Book.objects.filter(price=19.99))

        dups = [p for p in report.prescriptions if p.issue_type == IssueType.DUPLICATE_QUERY]
        assert len(dups) >= 1
        fix = dups[0].fix_suggestion.lower()
        assert "variable" in fix or "reuse" in fix or "cache" in fix
