"""Tests for the QuerySet Evaluation analyzer.

Verifies detection of inefficient queryset evaluation patterns like
len() vs .count(), bool() vs .exists(), list slicing vs .first().
"""

from __future__ import annotations

from unittest.mock import patch

from query_doctor.analyzers.queryset_eval import QuerySetEvalAnalyzer
from query_doctor.types import (
    CallSite,
    CapturedQuery,
    IssueType,
    Severity,
)


def _make_query(
    sql: str,
    callsite: CallSite | None = None,
    tables: list[str] | None = None,
) -> CapturedQuery:
    """Helper to create a CapturedQuery for testing."""
    return CapturedQuery(
        sql=sql,
        params=None,
        duration_ms=1.0,
        fingerprint="abc123",
        normalized_sql=sql,
        callsite=callsite,
        is_select=sql.strip().upper().startswith("SELECT"),
        tables=tables or [],
    )


class TestCountDetection:
    """Tests for len(qs) → qs.count() detection."""

    def test_select_all_with_len_callsite(self) -> None:
        """SELECT * with len() in code context should suggest .count()."""
        analyzer = QuerySetEvalAnalyzer()
        cs = CallSite(
            filepath="myapp/views.py",
            line_number=10,
            function_name="get_books",
            code_context="total = len(Book.objects.all())",
        )
        sql = 'SELECT "testapp_book"."id", "testapp_book"."title" FROM "testapp_book"'
        queries = [_make_query(sql, callsite=cs)]

        results = analyzer.analyze(queries)

        assert len(results) >= 1
        assert results[0].issue_type == IssueType.QUERYSET_EVAL
        assert ".count()" in results[0].fix_suggestion

    def test_len_with_filter(self) -> None:
        """len() on filtered queryset should still suggest .count()."""
        analyzer = QuerySetEvalAnalyzer()
        cs = CallSite(
            filepath="myapp/views.py",
            line_number=15,
            function_name="get_count",
            code_context="count = len(qs.filter(active=True))",
        )
        sql = (
            'SELECT "testapp_book"."id" FROM "testapp_book" '
            'WHERE "testapp_book"."published_date" IS NOT NULL'
        )
        queries = [_make_query(sql, callsite=cs)]

        results = analyzer.analyze(queries)

        assert len(results) >= 1
        assert ".count()" in results[0].fix_suggestion


class TestExistsDetection:
    """Tests for bool(qs)/if qs → qs.exists() detection."""

    def test_bool_check_suggests_exists(self) -> None:
        """bool() or if-check on queryset should suggest .exists()."""
        analyzer = QuerySetEvalAnalyzer()
        cs = CallSite(
            filepath="myapp/views.py",
            line_number=20,
            function_name="check_books",
            code_context="if Book.objects.filter(active=True):",
        )
        sql = (
            'SELECT "testapp_book"."id", "testapp_book"."title" '
            'FROM "testapp_book" WHERE "testapp_book"."published_date" IS NOT NULL'
        )
        queries = [_make_query(sql, callsite=cs)]

        results = analyzer.analyze(queries)

        assert len(results) >= 1
        assert ".exists()" in results[0].fix_suggestion

    def test_bool_explicit(self) -> None:
        """Explicit bool() call should suggest .exists()."""
        analyzer = QuerySetEvalAnalyzer()
        cs = CallSite(
            filepath="myapp/views.py",
            line_number=25,
            function_name="has_books",
            code_context="has_books = bool(Book.objects.all())",
        )
        sql = 'SELECT "testapp_book"."id" FROM "testapp_book"'
        queries = [_make_query(sql, callsite=cs)]

        results = analyzer.analyze(queries)

        assert len(results) >= 1
        assert ".exists()" in results[0].fix_suggestion


class TestFirstDetection:
    """Tests for list(qs)[0] → qs.first() detection."""

    def test_list_index_suggests_first(self) -> None:
        """list(qs)[0] pattern should suggest .first()."""
        analyzer = QuerySetEvalAnalyzer()
        cs = CallSite(
            filepath="myapp/views.py",
            line_number=30,
            function_name="get_first_book",
            code_context="book = list(Book.objects.all())[0]",
        )
        sql = 'SELECT "testapp_book"."id", "testapp_book"."title" FROM "testapp_book"'
        queries = [_make_query(sql, callsite=cs)]

        results = analyzer.analyze(queries)

        assert len(results) >= 1
        assert ".first()" in results[0].fix_suggestion


class TestNegativeCases:
    """Tests that valid patterns are not flagged."""

    def test_no_callsite_no_detection(self) -> None:
        """Without callsite, evaluation patterns cannot be detected."""
        analyzer = QuerySetEvalAnalyzer()
        sql = 'SELECT "testapp_book"."id" FROM "testapp_book"'
        queries = [_make_query(sql)]

        results = analyzer.analyze(queries)

        assert len(results) == 0

    def test_normal_code_not_flagged(self) -> None:
        """Normal code without problematic patterns should not flag."""
        analyzer = QuerySetEvalAnalyzer()
        cs = CallSite(
            filepath="myapp/views.py",
            line_number=40,
            function_name="get_books",
            code_context="books = list(Book.objects.select_related('author'))",
        )
        sql = 'SELECT "testapp_book"."id" FROM "testapp_book"'
        queries = [_make_query(sql, callsite=cs)]

        results = analyzer.analyze(queries)

        # list() alone without [0] should not flag for .first()
        # and list() is not len() or bool()
        assert all(".first()" not in r.fix_suggestion for r in results)

    def test_empty_queries(self) -> None:
        """Empty query list should return no prescriptions."""
        analyzer = QuerySetEvalAnalyzer()
        assert analyzer.analyze([]) == []

    def test_non_select_not_flagged(self) -> None:
        """Non-SELECT queries should not be analyzed."""
        analyzer = QuerySetEvalAnalyzer()
        cs = CallSite(
            filepath="myapp/views.py",
            line_number=50,
            function_name="create",
            code_context="len(Book.objects.all())",
        )
        sql = 'INSERT INTO "testapp_book" ("title") VALUES (?)'
        queries = [
            CapturedQuery(
                sql=sql,
                params=None,
                duration_ms=1.0,
                fingerprint="def456",
                normalized_sql=sql,
                callsite=cs,
                is_select=False,
                tables=[],
            )
        ]

        results = analyzer.analyze(queries)

        assert len(results) == 0


class TestEdgeCases:
    """Edge cases for the QuerySet Evaluation analyzer."""

    def test_analyzer_name(self) -> None:
        """Analyzer name should be set correctly."""
        analyzer = QuerySetEvalAnalyzer()
        assert analyzer.name == "queryset_eval"

    def test_severity_is_info(self) -> None:
        """QuerySet evaluation issues should have INFO severity."""
        analyzer = QuerySetEvalAnalyzer()
        cs = CallSite(
            filepath="myapp/views.py",
            line_number=10,
            function_name="count_books",
            code_context="total = len(Book.objects.all())",
        )
        sql = 'SELECT "testapp_book"."id" FROM "testapp_book"'
        queries = [_make_query(sql, callsite=cs)]

        results = analyzer.analyze(queries)

        assert len(results) >= 1
        assert results[0].severity == Severity.INFO

    def test_never_crashes_on_weird_input(self) -> None:
        """Analyzer should never raise on unexpected input."""
        analyzer = QuerySetEvalAnalyzer()
        cs = CallSite(
            filepath="",
            line_number=0,
            function_name="",
            code_context="",
        )
        queries = [
            _make_query("", callsite=cs),
            _make_query("SELECT FROM", callsite=cs),
        ]
        results = analyzer.analyze(queries)
        assert isinstance(results, list)

    def test_multiple_issues_detected(self) -> None:
        """Multiple evaluation issues should each be reported."""
        analyzer = QuerySetEvalAnalyzer()
        queries = [
            _make_query(
                'SELECT "t"."id" FROM "t"',
                callsite=CallSite("a.py", 1, "f", "len(qs)"),
            ),
            _make_query(
                'SELECT "t"."id" FROM "t" WHERE "t"."x" = ?',
                callsite=CallSite("b.py", 2, "g", "if qs.filter(x=1):"),
            ),
        ]

        results = analyzer.analyze(queries)

        assert len(results) >= 2

    def test_disabled_via_config(self) -> None:
        """Analyzer should return empty when disabled in config."""
        disabled_config = {
            "ANALYZERS": {"queryset_eval": {"enabled": False}},
            "ENABLED": True,
            "SAMPLE_RATE": 1.0,
            "CAPTURE_STACK_TRACES": True,
            "STACK_TRACE_EXCLUDE": [],
            "REPORTERS": ["console"],
            "IGNORE_PATTERNS": [],
            "IGNORE_URLS": [],
            "QUERY_BUDGET": {"DEFAULT_MAX_QUERIES": None, "DEFAULT_MAX_TIME_MS": None},
        }
        with patch("query_doctor.conf.get_config", return_value=disabled_config):
            analyzer = QuerySetEvalAnalyzer()
            cs = CallSite("a.py", 1, "f", "len(qs)")
            queries = [_make_query('SELECT "t"."id" FROM "t"', callsite=cs)]
            results = analyzer.analyze(queries)
            assert results == []
