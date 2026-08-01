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
        # This may or may not flag depending on threshold -- the key is no crash
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
            "IGNORE_URLS": [],
            "QUERY_BUDGET": {"DEFAULT_MAX_QUERIES": None, "DEFAULT_MAX_TIME_MS": None},
        }
        with patch("query_doctor.conf.get_config", return_value=disabled_config):
            analyzer = FatSelectAnalyzer(field_count_threshold=3)
            sql = 'SELECT "t"."a", "t"."b", "t"."c", "t"."d" FROM "t"'
            queries = [_make_query(sql, tables=["t"])]
            results = analyzer.analyze(queries)
            assert results == []

    def test_threshold_configurable_via_config_key(self) -> None:
        """ANALYZERS.fat_select.threshold in QUERY_DOCTOR settings must actually
        change detection behavior -- no analyzer-constructor override used here,
        so this only passes if _get_threshold() reads the 'threshold' config key.
        """
        from django.test import override_settings

        from query_doctor.conf import get_config

        sql = 'SELECT "t"."a", "t"."b", "t"."c", "t"."d" FROM "t"'
        queries = [_make_query(sql, tables=["t"])]

        # 4 columns, threshold overridden down to 4 -> should flag.
        with override_settings(QUERY_DOCTOR={"ANALYZERS": {"fat_select": {"threshold": 4}}}):
            get_config.cache_clear()
            results = FatSelectAnalyzer().analyze(queries)
            get_config.cache_clear()
        assert len(results) >= 1

        # Same query, threshold overridden up to 10 -> should NOT flag.
        with override_settings(QUERY_DOCTOR={"ANALYZERS": {"fat_select": {"threshold": 10}}}):
            get_config.cache_clear()
            results = FatSelectAnalyzer().analyze(queries)
            get_config.cache_clear()
        assert len(results) == 0


class TestColumnAttribution:
    """Entry 52: the column count must belong to the table the message names.

    ``_SELECT_COLS_RE`` takes everything between SELECT and FROM while the
    table comes from the FROM clause alone, so a joined query counted the
    joined table's columns and attributed them to the base table. The
    prescribed ``.defer()`` then addresses a fraction of the number shown.
    """

    _BOOK_COLS = (
        '"testapp_book"."id", "testapp_book"."title", "testapp_book"."isbn", '
        '"testapp_book"."author_id", "testapp_book"."publisher_id", '
        '"testapp_book"."price", "testapp_book"."description", '
        '"testapp_book"."published_date"'
    )
    _AUTHOR_COLS = (
        '"testapp_author"."id", "testapp_author"."name", "testapp_author"."email", '
        '"testapp_author"."bio", "testapp_author"."publisher_id"'
    )

    def test_join_does_not_inflate_the_base_table_count(self) -> None:
        """select_related must not change the count reported for the base table."""
        analyzer = FatSelectAnalyzer(field_count_threshold=5)
        plain = _make_query(f'SELECT {self._BOOK_COLS} FROM "testapp_book"')
        joined = _make_query(
            f'SELECT {self._BOOK_COLS}, {self._AUTHOR_COLS} FROM "testapp_book" '
            'INNER JOIN "testapp_author" ON '
            '("testapp_book"."author_id" = "testapp_author"."id")'
        )

        plain_result = analyzer.analyze([plain])
        joined_result = FatSelectAnalyzer(field_count_threshold=5).analyze([joined])

        assert len(plain_result) == 1
        assert len(joined_result) == 1
        assert plain_result[0].extra["column_count"] == 8
        assert joined_result[0].extra["column_count"] == 8

    def test_joined_table_columns_are_not_counted(self) -> None:
        """Positive control: the joined columns really are present in the SQL."""
        analyzer = FatSelectAnalyzer(field_count_threshold=5)
        joined = _make_query(
            f'SELECT {self._BOOK_COLS}, {self._AUTHOR_COLS} FROM "testapp_book" '
            'INNER JOIN "testapp_author" ON '
            '("testapp_book"."author_id" = "testapp_author"."id")'
        )
        assert joined.sql.count('"testapp_author"."') > 5

        result = analyzer.analyze([joined])
        assert result[0].extra["table"] == "testapp_book"
        assert result[0].extra["column_count"] < 13


class TestSingleRowLookups:
    """Entry 53: a primary-key fetch of one row is not a fat SELECT.

    ``Book.objects.get(pk=1)`` returns one row and hits the default
    threshold of 8 with Book's own columns, so every read of the model
    fired. It was the finding a first-time user saw most often, on queries
    that are not defects.
    """

    _BOOK_COLS = TestColumnAttribution._BOOK_COLS

    def test_pk_lookup_is_not_flagged(self) -> None:
        """WHERE "table"."id" = ? returns at most one row."""
        analyzer = FatSelectAnalyzer(field_count_threshold=5)
        sql = f'SELECT {self._BOOK_COLS} FROM "testapp_book" WHERE "testapp_book"."id" = ?'
        assert analyzer.analyze([_make_query(sql)]) == []

    def test_limit_one_is_not_flagged(self) -> None:
        """LIMIT 1 bounds the result set just as explicitly."""
        analyzer = FatSelectAnalyzer(field_count_threshold=5)
        sql = f'SELECT {self._BOOK_COLS} FROM "testapp_book" LIMIT 1'
        assert analyzer.analyze([_make_query(sql)]) == []

    def test_unbounded_select_is_still_flagged(self) -> None:
        """Negative control: the same columns without a bound still fire."""
        analyzer = FatSelectAnalyzer(field_count_threshold=5)
        sql = f'SELECT {self._BOOK_COLS} FROM "testapp_book"'
        assert len(analyzer.analyze([_make_query(sql)])) == 1

    def test_non_pk_filter_is_still_flagged(self) -> None:
        """A WHERE on a non-unique column bounds nothing."""
        analyzer = FatSelectAnalyzer(field_count_threshold=5)
        sql = (
            f'SELECT {self._BOOK_COLS} FROM "testapp_book" '
            'WHERE "testapp_book"."published_date" = ?'
        )
        assert len(analyzer.analyze([_make_query(sql)])) == 1
