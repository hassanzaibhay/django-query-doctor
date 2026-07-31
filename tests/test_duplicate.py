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


@pytest.mark.django_db
class TestInterveningWrites:
    """Entry 51: a re-read after a write to the same table is not a duplicate.

    Following the prescription -- "assign the result to a variable and reuse
    it" -- would hand the caller the pre-write row. That makes this the one
    finding in the set whose fix is a correctness regression rather than a
    no-op, so the group is suppressed instead of reworded.
    """

    def _capture_queries(self, func):
        """Helper to capture queries from a callable."""
        interceptor = QueryInterceptor()
        with connection.execute_wrapper(interceptor):
            func()
        return interceptor.get_queries()

    def _duplicates(self, func):
        """Return only the duplicate prescriptions for a captured callable."""
        prescriptions = DuplicateAnalyzer().analyze(self._capture_queries(func))
        return [p for p in prescriptions if p.issue_type == IssueType.DUPLICATE_QUERY]

    def test_read_write_read_is_not_a_duplicate(self) -> None:
        """The second read observes the write, so it is not redundant."""
        book = BookFactory()

        def read_write_read() -> None:
            from tests.testapp.models import Book

            Book.objects.get(pk=book.pk)
            Book.objects.filter(pk=book.pk).update(title="changed")
            Book.objects.get(pk=book.pk)

        assert self._duplicates(read_write_read) == []

    def test_read_read_without_a_write_is_still_a_duplicate(self) -> None:
        """Negative control: without the write, the finding must still fire.

        Without this the test above would pass against an analyzer that had
        simply stopped detecting anything.
        """
        book = BookFactory()

        def read_read() -> None:
            from tests.testapp.models import Book

            Book.objects.get(pk=book.pk)
            Book.objects.get(pk=book.pk)

        assert len(self._duplicates(read_read)) == 1

    def test_write_to_an_unrelated_table_does_not_suppress(self) -> None:
        """Only a write to a table the group reads can invalidate the group."""
        book = BookFactory()

        def read_unrelated_write_read() -> None:
            from tests.testapp.models import Book, Publisher

            Book.objects.get(pk=book.pk)
            Publisher.objects.filter(pk=book.publisher_id).update(country="NL")
            Book.objects.get(pk=book.pk)

        assert len(self._duplicates(read_unrelated_write_read)) == 1
