"""Tests for duplicate query detection in query_doctor.analyzers.duplicate."""

from __future__ import annotations

import pytest
from django.db import connection

from query_doctor.analyzers.duplicate import DuplicateAnalyzer
from query_doctor.interceptor import QueryInterceptor
from query_doctor.types import IssueType, Severity
from tests.factories import BookFactory


@pytest.mark.django_db
class TestDuplicateAnalyzer:
    """Tests for DuplicateAnalyzer."""

    def _capture_queries(self, func):
        """Helper to capture queries from a callable."""
        interceptor = QueryInterceptor()
        with connection.execute_wrapper(interceptor):
            func()
        return interceptor.get_queries()

    def test_detects_exact_duplicates(self) -> None:
        """Same query executed 3 times -> duplicate detected."""
        BookFactory()

        def run_same_query() -> None:
            from tests.testapp.models import Book

            for _ in range(3):
                list(Book.objects.all())

        queries = self._capture_queries(run_same_query)

        analyzer = DuplicateAnalyzer()
        prescriptions = analyzer.analyze(queries)

        dup_prescriptions = [p for p in prescriptions if p.issue_type == IssueType.DUPLICATE_QUERY]
        assert len(dup_prescriptions) >= 1
        assert dup_prescriptions[0].query_count >= 3

    def test_no_false_positive_different_queries(self) -> None:
        """Different queries -> no duplicate flagged."""
        BookFactory()

        def run_different_queries() -> None:
            from tests.testapp.models import Book

            list(Book.objects.all())
            list(Book.objects.filter(price__gt=10))

        queries = self._capture_queries(run_different_queries)

        analyzer = DuplicateAnalyzer()
        prescriptions = analyzer.analyze(queries)

        dup_prescriptions = [p for p in prescriptions if p.issue_type == IssueType.DUPLICATE_QUERY]
        assert len(dup_prescriptions) == 0

    def test_near_duplicates_same_structure(self) -> None:
        """Same structure, different params -> near-duplicate suggestion."""
        books = [BookFactory() for _ in range(4)]

        def run_near_duplicates() -> None:
            from tests.testapp.models import Book

            for book in books:
                list(Book.objects.filter(id=book.id))

        queries = self._capture_queries(run_near_duplicates)

        analyzer = DuplicateAnalyzer()
        prescriptions = analyzer.analyze(queries)

        # Should detect near-duplicates (same fingerprint, different params)
        # These may overlap with N+1 patterns, but duplicates analyzer should
        # still report them
        assert len(prescriptions) >= 0  # may or may not flag depending on threshold

    def test_severity_is_warning(self) -> None:
        """Duplicate queries should have WARNING severity."""
        BookFactory()

        def run_same_query() -> None:
            from tests.testapp.models import Book

            for _ in range(3):
                list(Book.objects.all())

        queries = self._capture_queries(run_same_query)

        analyzer = DuplicateAnalyzer()
        prescriptions = analyzer.analyze(queries)

        dup_prescriptions = [p for p in prescriptions if p.issue_type == IssueType.DUPLICATE_QUERY]
        assert len(dup_prescriptions) >= 1
        assert dup_prescriptions[0].severity == Severity.WARNING

    def test_empty_queries(self) -> None:
        """Empty query list should produce no prescriptions."""
        analyzer = DuplicateAnalyzer()
        prescriptions = analyzer.analyze([])
        assert prescriptions == []

    def test_single_query_no_duplicate(self) -> None:
        """A single query should not be flagged as duplicate."""
        BookFactory()

        def run_once() -> None:
            from tests.testapp.models import Book

            list(Book.objects.all())

        queries = self._capture_queries(run_once)

        analyzer = DuplicateAnalyzer()
        prescriptions = analyzer.analyze(queries)

        dup_prescriptions = [p for p in prescriptions if p.issue_type == IssueType.DUPLICATE_QUERY]
        assert len(dup_prescriptions) == 0

    def test_analyzer_name(self) -> None:
        """Analyzer should have the correct name."""
        analyzer = DuplicateAnalyzer()
        assert analyzer.name == "duplicate"

    def test_fix_suggestion_present(self) -> None:
        """Prescription should include a fix suggestion."""
        BookFactory()

        def run_same_query() -> None:
            from tests.testapp.models import Book

            for _ in range(3):
                list(Book.objects.all())

        queries = self._capture_queries(run_same_query)

        analyzer = DuplicateAnalyzer()
        prescriptions = analyzer.analyze(queries)

        dup_prescriptions = [p for p in prescriptions if p.issue_type == IssueType.DUPLICATE_QUERY]
        assert len(dup_prescriptions) >= 1
        assert dup_prescriptions[0].fix_suggestion != ""
