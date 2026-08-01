"""Tests for N+1 query detection in query_doctor.analyzers.nplusone.

This is the most critical test file. It validates that the N+1 analyzer
correctly detects FK and M2M N+1 patterns, generates proper prescriptions,
and avoids false positives when select_related/prefetch_related is used.
"""

from __future__ import annotations

import pytest
from django.db import connection

from query_doctor.analyzers.nplusone import NPlusOneAnalyzer
from query_doctor.interceptor import QueryInterceptor
from query_doctor.types import IssueType, Severity
from tests.factories import BookFactory, CategoryFactory


@pytest.mark.django_db
class TestNPlusOneAnalyzer:
    """Tests for NPlusOneAnalyzer."""

    def _capture_queries(self, func):
        """Helper to capture queries from a callable."""
        interceptor = QueryInterceptor()
        with connection.execute_wrapper(interceptor):
            func()
        return interceptor.get_queries()

    def test_detects_fk_nplusone(self) -> None:
        """Iterating books and accessing .author without select_related -> N+1."""
        # Create 5 books with different authors
        for _ in range(5):
            BookFactory()

        queries = self._capture_queries(lambda: [book.author.name for book in Book.objects.all()])

        analyzer = NPlusOneAnalyzer()
        prescriptions = analyzer.analyze(queries)

        # Should detect N+1 for author access
        nplusone_prescriptions = [p for p in prescriptions if p.issue_type == IssueType.N_PLUS_ONE]
        assert len(nplusone_prescriptions) >= 1

        # Should suggest select_related('author')
        author_rx = [p for p in nplusone_prescriptions if "select_related" in p.fix_suggestion]
        assert len(author_rx) >= 1
        assert any("author" in p.fix_suggestion for p in author_rx)

    def test_no_false_positive_with_select_related(self) -> None:
        """Using select_related -> no N+1 reported."""
        for _ in range(5):
            BookFactory()

        queries = self._capture_queries(
            lambda: [book.author.name for book in Book.objects.select_related("author").all()]
        )

        analyzer = NPlusOneAnalyzer()
        prescriptions = analyzer.analyze(queries)

        # Should not detect N+1 for author
        nplusone_prescriptions = [p for p in prescriptions if p.issue_type == IssueType.N_PLUS_ONE]
        # Filter to only author-related ones
        author_prescriptions = [
            p for p in nplusone_prescriptions if "author" in p.description.lower()
        ]
        assert len(author_prescriptions) == 0

    def test_detects_m2m_nplusone(self) -> None:
        """Iterating books and accessing .categories.all() without prefetch -> N+1."""
        categories = [CategoryFactory() for _ in range(3)]
        for _ in range(5):
            book = BookFactory()
            book.categories.set(categories)

        queries = self._capture_queries(
            lambda: [list(book.categories.all()) for book in Book.objects.all()]
        )

        analyzer = NPlusOneAnalyzer()
        prescriptions = analyzer.analyze(queries)

        nplusone_prescriptions = [p for p in prescriptions if p.issue_type == IssueType.N_PLUS_ONE]
        assert len(nplusone_prescriptions) >= 1

        # Should suggest prefetch_related for M2M
        m2m_rx = [p for p in nplusone_prescriptions if "prefetch_related" in p.fix_suggestion]
        assert len(m2m_rx) >= 1

    def test_multiple_nplusone_patterns(self) -> None:
        """Accessing both .author and .publisher -> 2 separate prescriptions."""
        for _ in range(5):
            BookFactory()

        def access_both() -> None:
            for book in Book.objects.all():
                _ = book.author.name
                _ = book.publisher.name

        queries = self._capture_queries(access_both)

        analyzer = NPlusOneAnalyzer()
        prescriptions = analyzer.analyze(queries)

        nplusone_prescriptions = [p for p in prescriptions if p.issue_type == IssueType.N_PLUS_ONE]
        # Should detect at least 2 different N+1 patterns
        assert len(nplusone_prescriptions) >= 2

    def test_below_threshold_not_flagged(self) -> None:
        """Only 2 similar queries (below default threshold 3) -> no issue."""
        # Create only 2 books
        for _ in range(2):
            BookFactory()

        queries = self._capture_queries(lambda: [book.author.name for book in Book.objects.all()])

        analyzer = NPlusOneAnalyzer()
        prescriptions = analyzer.analyze(queries)

        # With only 2 books, there are only 2 author queries (below threshold=3)
        nplusone_prescriptions = [p for p in prescriptions if p.issue_type == IssueType.N_PLUS_ONE]
        assert len(nplusone_prescriptions) == 0

    def test_severity_critical_for_many_queries(self) -> None:
        """10+ N+1 queries should be CRITICAL severity."""
        for _ in range(12):
            BookFactory()

        queries = self._capture_queries(lambda: [book.author.name for book in Book.objects.all()])

        analyzer = NPlusOneAnalyzer()
        prescriptions = analyzer.analyze(queries)

        nplusone_prescriptions = [p for p in prescriptions if p.issue_type == IssueType.N_PLUS_ONE]
        assert len(nplusone_prescriptions) >= 1
        # 12 queries should be CRITICAL
        assert any(p.severity == Severity.CRITICAL for p in nplusone_prescriptions)

    def test_severity_warning_for_few_queries(self) -> None:
        """3-9 N+1 queries should be WARNING severity."""
        for _ in range(4):
            BookFactory()

        queries = self._capture_queries(lambda: [book.author.name for book in Book.objects.all()])

        analyzer = NPlusOneAnalyzer()
        prescriptions = analyzer.analyze(queries)

        nplusone_prescriptions = [p for p in prescriptions if p.issue_type == IssueType.N_PLUS_ONE]
        assert len(nplusone_prescriptions) >= 1
        assert any(p.severity == Severity.WARNING for p in nplusone_prescriptions)

    def test_prescription_has_query_count(self) -> None:
        """Prescription should report how many queries the N+1 involves."""
        for _ in range(5):
            BookFactory()

        queries = self._capture_queries(lambda: [book.author.name for book in Book.objects.all()])

        analyzer = NPlusOneAnalyzer()
        prescriptions = analyzer.analyze(queries)

        nplusone_prescriptions = [p for p in prescriptions if p.issue_type == IssueType.N_PLUS_ONE]
        assert len(nplusone_prescriptions) >= 1
        assert nplusone_prescriptions[0].query_count >= 5

    def test_no_false_positive_single_query(self) -> None:
        """A single query should not be flagged as N+1."""
        BookFactory()

        queries = self._capture_queries(lambda: list(Book.objects.all()))

        analyzer = NPlusOneAnalyzer()
        prescriptions = analyzer.analyze(queries)

        nplusone_prescriptions = [p for p in prescriptions if p.issue_type == IssueType.N_PLUS_ONE]
        assert len(nplusone_prescriptions) == 0

    def test_empty_queries(self) -> None:
        """Empty query list should produce no prescriptions."""
        analyzer = NPlusOneAnalyzer()
        prescriptions = analyzer.analyze([])
        assert prescriptions == []

    def test_analyzer_name(self) -> None:
        """Analyzer should have the correct name."""
        analyzer = NPlusOneAnalyzer()
        assert analyzer.name == "nplusone"


@pytest.mark.django_db
class TestPrescriptionsResolveOnRealModels:
    """Every field a prescription names must exist on the model it names.

    These tests assert on behaviour: the prescribed queryset call is *run*
    against real Django, so a field that does not resolve fails with the
    FieldError/ValueError Django itself raises rather than with a string
    comparison that a reworded message would silently satisfy.
    """

    def _capture_queries(self, func):
        """Helper to capture queries from a callable."""
        interceptor = QueryInterceptor()
        with connection.execute_wrapper(interceptor):
            func()
        return interceptor.get_queries()

    def _apply(self, rx) -> None:
        """Run whatever relation the prescription names, or its bulk fetch.

        Raises whatever Django raises. A prescription that names no relation
        is exercised through its bulk-fetch advice instead, so every code
        path this test covers ends in a real query.
        """
        from django.apps import apps

        model = apps.get_model(rx.extra["model"])
        field = rx.extra.get("field")
        strategy = rx.extra["strategy"]
        if strategy == "select_related":
            list(model.objects.select_related(field)[:1])
        elif strategy == "prefetch_related":
            list(model.objects.prefetch_related(field)[:1])
        else:
            assert strategy == "bulk_fetch", strategy
            assert field is None
            list(model.objects.filter(pk__in=[1, 2, 3]))

    def test_pk_loop_prescription_is_applicable(self) -> None:
        """`Model.objects.get(pk=...)` in a loop must not prescribe a bad field.

        Entry 49: no relation is traversed here, so `select_related` cannot
        help and the field name was previously sliced off the table name.
        """
        for _ in range(5):
            BookFactory()
        ids = list(Author.objects.values_list("id", flat=True))

        def loop() -> None:
            for pk in ids:
                Author.objects.get(pk=pk)

        queries = self._capture_queries(loop)
        analyzer = NPlusOneAnalyzer()
        rxs = [p for p in analyzer.analyze(queries) if p.issue_type == IssueType.N_PLUS_ONE]

        assert rxs, "positive control: the N+1 itself must still be detected"
        for rx in rxs:
            self._apply(rx)

    def test_pk_loop_prescribes_a_bulk_fetch(self) -> None:
        """With no relation traversed, the advice is a bulk fetch, not a join."""
        for _ in range(5):
            BookFactory()
        ids = list(Author.objects.values_list("id", flat=True))

        def loop() -> None:
            for pk in ids:
                Author.objects.get(pk=pk)

        queries = self._capture_queries(loop)
        analyzer = NPlusOneAnalyzer()
        rxs = [p for p in analyzer.analyze(queries) if p.issue_type == IssueType.N_PLUS_ONE]

        assert len(rxs) == 1
        assert rxs[0].extra["strategy"] == "bulk_fetch"
        # The fixer keys off these tokens; neither may appear, or fix_queries
        # would write an unapplicable call onto the callsite line.
        assert "select_related(" not in rxs[0].fix_suggestion
        assert "prefetch_related(" not in rxs[0].fix_suggestion
        assert "in_bulk" in rxs[0].fix_suggestion

    def test_forward_fk_traversal_still_prescribes_select_related(self) -> None:
        """Positive control: a real forward-FK N+1 keeps the join advice."""
        for _ in range(5):
            BookFactory()

        queries = self._capture_queries(lambda: [book.author.name for book in Book.objects.all()])
        analyzer = NPlusOneAnalyzer()
        rxs = [p for p in analyzer.analyze(queries) if p.issue_type == IssueType.N_PLUS_ONE]

        joins = [p for p in rxs if p.extra["strategy"] == "select_related"]
        assert len(joins) == 1
        assert joins[0].extra["field"] == "author"
        assert joins[0].extra["model"] == "testapp.Book"
        self._apply(joins[0])

    def test_reverse_fk_prescription_is_applicable(self) -> None:
        """Iterating authors and reading `.books` prescribes the reverse accessor.

        The FK column is `testapp_book.author_id`, so the field name read off
        the column is `author` -- which is a field on Book, not on Author, and
        `Author.objects.prefetch_related('author')` raises.
        """
        for _ in range(5):
            BookFactory()

        def loop() -> None:
            for author in Author.objects.all():
                list(author.books.all())

        queries = self._capture_queries(loop)
        analyzer = NPlusOneAnalyzer()
        rxs = [p for p in analyzer.analyze(queries) if p.issue_type == IssueType.N_PLUS_ONE]

        assert rxs, "positive control: the reverse-FK N+1 must still be detected"
        for rx in rxs:
            self._apply(rx)

    def test_m2m_prescription_is_applicable(self) -> None:
        """The M2M through-table branch must also resolve on the model it names."""
        categories = [CategoryFactory() for _ in range(3)]
        for _ in range(5):
            book = BookFactory()
            book.categories.set(categories)

        queries = self._capture_queries(
            lambda: [list(book.categories.all()) for book in Book.objects.all()]
        )
        analyzer = NPlusOneAnalyzer()
        rxs = [p for p in analyzer.analyze(queries) if p.issue_type == IssueType.N_PLUS_ONE]

        assert rxs, "positive control: the M2M N+1 must still be detected"
        for rx in rxs:
            self._apply(rx)


# Import here to make model references work in lambdas above
from tests.testapp.models import Author, Book  # noqa: E402
