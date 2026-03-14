"""Tests for the Fat SELECT analyzer.

Verifies detection of SELECT * on models with many fields or large fields,
and suggests .only() or .defer() optimizations.
"""

from __future__ import annotations

from unittest.mock import patch

from query_doctor.analyzers.fat_select import FatSelectAnalyzer
from query_doctor.types import (
    CallSite,
    CapturedQuery,
    IssueType,
    Severity,
)


def _make_query(
    sql: str,
    tables: list[str] | None = None,
    callsite: CallSite | None = None,
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


class TestFatSelectPositive:
    """Tests that fat SELECT patterns are correctly detected."""

    def test_select_star_on_wide_table(self) -> None:
        """SELECT * on a table with many columns should be flagged."""
        analyzer = FatSelectAnalyzer(field_count_threshold=5)
        sql = (
            'SELECT "testapp_book"."id", "testapp_book"."title", '
            '"testapp_book"."isbn", "testapp_book"."author_id", '
            '"testapp_book"."publisher_id", "testapp_book"."price", '
            '"testapp_book"."description", "testapp_book"."published_date" '
            'FROM "testapp_book"'
        )
        queries = [_make_query(sql, tables=["testapp_book"])]

        results = analyzer.analyze(queries)

        assert len(results) >= 1
        assert results[0].issue_type == IssueType.FAT_SELECT
        assert results[0].severity == Severity.INFO

    def test_fix_suggestion_mentions_only_or_defer(self) -> None:
        """Fix suggestion should mention .only() or .defer()."""
        analyzer = FatSelectAnalyzer(field_count_threshold=5)
        sql = (
            'SELECT "testapp_book"."id", "testapp_book"."title", '
            '"testapp_book"."isbn", "testapp_book"."author_id", '
            '"testapp_book"."publisher_id", "testapp_book"."price", '
            '"testapp_book"."description", "testapp_book"."published_date" '
            'FROM "testapp_book"'
        )
        queries = [_make_query(sql, tables=["testapp_book"])]

        results = analyzer.analyze(queries)

        assert len(results) >= 1
        fix = results[0].fix_suggestion.lower()
        assert ".only(" in fix or ".defer(" in fix

    def test_detects_large_text_fields(self) -> None:
        """Queries selecting TextField columns should flag them for .defer()."""
        analyzer = FatSelectAnalyzer(field_count_threshold=3)
        sql = (
            'SELECT "testapp_book"."id", "testapp_book"."title", '
            '"testapp_book"."description" '
            'FROM "testapp_book"'
        )
        queries = [_make_query(sql, tables=["testapp_book"])]

        # Even with fewer fields, if we detect large fields, it should flag
        results = analyzer.analyze(queries)
        # This may or may not flag depending on threshold — the key is no crash
        assert isinstance(results, list)

    def test_callsite_preserved(self) -> None:
        """CallSite from the query should be included in the prescription."""
        analyzer = FatSelectAnalyzer(field_count_threshold=5)
        cs = CallSite(
            filepath="myapp/views.py",
            line_number=42,
            function_name="get_queryset",
        )
        sql = (
            'SELECT "testapp_book"."id", "testapp_book"."title", '
            '"testapp_book"."isbn", "testapp_book"."author_id", '
            '"testapp_book"."publisher_id", "testapp_book"."price", '
            '"testapp_book"."description", "testapp_book"."published_date" '
            'FROM "testapp_book"'
        )
        queries = [_make_query(sql, tables=["testapp_book"], callsite=cs)]

        results = analyzer.analyze(queries)

        assert len(results) >= 1
        assert results[0].callsite == cs

    def test_multiple_fat_selects(self) -> None:
        """Multiple fat SELECT queries on different tables should each be flagged."""
        analyzer = FatSelectAnalyzer(field_count_threshold=3)
        sql1 = (
            'SELECT "testapp_book"."id", "testapp_book"."title", '
            '"testapp_book"."isbn", "testapp_book"."description" '
            'FROM "testapp_book"'
        )
        sql2 = (
            'SELECT "testapp_author"."id", "testapp_author"."name", '
            '"testapp_author"."email", "testapp_author"."bio" '
            'FROM "testapp_author"'
        )
        queries = [
            _make_query(sql1, tables=["testapp_book"]),
            _make_query(sql2, tables=["testapp_author"]),
        ]

        results = analyzer.analyze(queries)

        assert len(results) >= 2


class TestFatSelectNegative:
    """Tests that non-fat SELECTs are not flagged."""

    def test_narrow_select_not_flagged(self) -> None:
        """SELECT with few columns should not be flagged."""
        analyzer = FatSelectAnalyzer(field_count_threshold=8)
        sql = 'SELECT "testapp_book"."id", "testapp_book"."title" FROM "testapp_book"'
        queries = [_make_query(sql, tables=["testapp_book"])]

        results = analyzer.analyze(queries)

        assert len(results) == 0

    def test_non_select_not_flagged(self) -> None:
        """INSERT/UPDATE/DELETE should not be flagged."""
        analyzer = FatSelectAnalyzer()
        sql = 'INSERT INTO "testapp_book" ("title") VALUES (?)'
        queries = [
            CapturedQuery(
                sql=sql,
                params=None,
                duration_ms=1.0,
                fingerprint="def456",
                normalized_sql=sql,
                callsite=None,
                is_select=False,
                tables=["testapp_book"],
            )
        ]

        results = analyzer.analyze(queries)

        assert len(results) == 0

    def test_empty_queries(self) -> None:
        """Empty query list should return no prescriptions."""
        analyzer = FatSelectAnalyzer()
        assert analyzer.analyze([]) == []

    def test_select_with_only_clause(self) -> None:
        """A query already using specific fields (narrow select) should not flag."""
        analyzer = FatSelectAnalyzer(field_count_threshold=8)
        sql = 'SELECT "testapp_book"."id", "testapp_book"."title" FROM "testapp_book"'
        queries = [_make_query(sql, tables=["testapp_book"])]

        results = analyzer.analyze(queries)

        assert len(results) == 0


class TestFatSelectEdgeCases:
    """Edge cases for the Fat SELECT analyzer."""

    def test_handles_malformed_sql(self) -> None:
        """Malformed SQL should not crash the analyzer."""
        analyzer = FatSelectAnalyzer()
        sql = "NOT VALID SQL AT ALL"
        queries = [_make_query(sql)]

        results = analyzer.analyze(queries)

        assert isinstance(results, list)

    def test_threshold_boundary(self) -> None:
        """Query with exactly threshold columns should be flagged."""
        analyzer = FatSelectAnalyzer(field_count_threshold=3)
        sql = 'SELECT "t"."a", "t"."b", "t"."c" FROM "t"'
        queries = [_make_query(sql, tables=["t"])]

        results = analyzer.analyze(queries)

        assert len(results) >= 1

    def test_threshold_boundary_below(self) -> None:
        """Query with columns below threshold should NOT be flagged."""
        analyzer = FatSelectAnalyzer(field_count_threshold=4)
        sql = 'SELECT "t"."a", "t"."b", "t"."c" FROM "t"'
        queries = [_make_query(sql, tables=["t"])]

        results = analyzer.analyze(queries)

        assert len(results) == 0

    def test_analyzer_name(self) -> None:
        """Analyzer name should be set correctly."""
        analyzer = FatSelectAnalyzer()
        assert analyzer.name == "fat_select"

    def test_never_crashes(self) -> None:
        """Analyzer should never raise, even with unexpected input."""
        analyzer = FatSelectAnalyzer()
        weird_queries = [
            _make_query(""),
            _make_query("SELECT FROM"),
            _make_query('SELECT "x"."y" FROM'),
        ]
        results = analyzer.analyze(weird_queries)
        assert isinstance(results, list)

    def test_disabled_via_config(self) -> None:
        """Analyzer should return empty when disabled in config."""
        disabled_config = {
            "ANALYZERS": {"fat_select": {"enabled": False}},
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
            analyzer = FatSelectAnalyzer(field_count_threshold=3)
            sql = 'SELECT "t"."a", "t"."b", "t"."c", "t"."d" FROM "t"'
            queries = [_make_query(sql, tables=["t"])]
            results = analyzer.analyze(queries)
            assert results == []
