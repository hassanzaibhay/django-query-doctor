"""Tests for the missing index analyzer.

Verifies that the analyzer correctly detects queries filtering or ordering
on non-indexed columns and suggests adding db_index=True or Meta.indexes.
"""

from __future__ import annotations

import pytest

from query_doctor.analyzers.missing_index import MissingIndexAnalyzer
from query_doctor.types import (
    CallSite,
    CapturedQuery,
    IssueType,
    Severity,
)

_BOOK_TABLE = "testapp_book"
_PUB_TABLE = "testapp_publisher"


def _make_query(
    sql: str,
    normalized_sql: str | None = None,
    tables: list[str] | None = None,
) -> CapturedQuery:
    """Helper to create a CapturedQuery for testing."""
    if normalized_sql is None:
        normalized_sql = sql.lower()
    return CapturedQuery(
        sql=sql,
        params=None,
        duration_ms=1.0,
        fingerprint="abc123",
        normalized_sql=normalized_sql,
        callsite=CallSite(filepath="views.py", line_number=10, function_name="get_queryset"),
        is_select=True,
        tables=tables or [],
    )


class TestMissingIndexAnalyzer:
    """Tests for MissingIndexAnalyzer."""

    def setup_method(self) -> None:
        """Set up analyzer instance."""
        self.analyzer = MissingIndexAnalyzer()

    def test_analyzer_name(self) -> None:
        """Analyzer should have the correct name."""
        assert self.analyzer.name == "missing_index"

    @pytest.mark.django_db
    def test_filter_on_non_indexed_field_detected(self) -> None:
        """Filtering on a non-indexed field should be detected."""
        # published_date on Book has NO index
        sql = 'SELECT * FROM "testapp_book" WHERE "testapp_book"."published_date" = \'2024-01-01\''
        norm = 'select * from "testapp_book" where "testapp_book"."published_date" = ?'
        query = _make_query(sql=sql, normalized_sql=norm, tables=[_BOOK_TABLE])
        prescriptions = self.analyzer.analyze([query])
        assert len(prescriptions) >= 1
        rx = prescriptions[0]
        assert rx.issue_type == IssueType.MISSING_INDEX
        assert "published_date" in rx.description
        assert "db_index" in rx.fix_suggestion or "indexes" in rx.fix_suggestion

    @pytest.mark.django_db
    def test_filter_on_indexed_field_not_detected(self) -> None:
        """Filtering on a field with db_index=True should NOT be detected."""
        # Publisher.country has db_index=True
        sql = 'SELECT * FROM "testapp_publisher" WHERE "testapp_publisher"."country" = \'US\''
        norm = 'select * from "testapp_publisher" where "testapp_publisher"."country" = ?'
        query = _make_query(sql=sql, normalized_sql=norm, tables=[_PUB_TABLE])
        prescriptions = self.analyzer.analyze([query])
        country_prescriptions = [p for p in prescriptions if "country" in p.description]
        assert len(country_prescriptions) == 0

    @pytest.mark.django_db
    def test_filter_on_fk_field_not_detected(self) -> None:
        """Filtering on a ForeignKey field should NOT be detected."""
        sql = 'SELECT * FROM "testapp_book" WHERE "testapp_book"."author_id" = 1'
        norm = 'select * from "testapp_book" where "testapp_book"."author_id" = ?'
        query = _make_query(sql=sql, normalized_sql=norm, tables=[_BOOK_TABLE])
        prescriptions = self.analyzer.analyze([query])
        author_prescriptions = [p for p in prescriptions if "author_id" in p.description]
        assert len(author_prescriptions) == 0

    @pytest.mark.django_db
    def test_order_by_non_indexed_field_detected(self) -> None:
        """ORDER BY on a non-indexed field should be detected."""
        sql = 'SELECT * FROM "testapp_book" ORDER BY "testapp_book"."published_date"'
        norm = 'select * from "testapp_book" order by "testapp_book"."published_date"'
        query = _make_query(sql=sql, normalized_sql=norm, tables=[_BOOK_TABLE])
        prescriptions = self.analyzer.analyze([query])
        assert len(prescriptions) >= 1
        assert any("published_date" in p.description for p in prescriptions)

    @pytest.mark.django_db
    def test_filter_on_pk_not_detected(self) -> None:
        """Filtering on the primary key should NOT be detected."""
        sql = 'SELECT * FROM "testapp_book" WHERE "testapp_book"."id" = 1'
        norm = 'select * from "testapp_book" where "testapp_book"."id" = ?'
        query = _make_query(sql=sql, normalized_sql=norm, tables=[_BOOK_TABLE])
        prescriptions = self.analyzer.analyze([query])
        id_prescriptions = [
            p for p in prescriptions if '"id"' in p.description or ".id" in p.description
        ]
        assert len(id_prescriptions) == 0

    @pytest.mark.django_db
    def test_filter_on_unique_field_not_detected(self) -> None:
        """Filtering on a unique field should NOT be detected."""
        sql = 'SELECT * FROM "testapp_book" WHERE "testapp_book"."isbn" = \'1234567890123\''
        norm = 'select * from "testapp_book" where "testapp_book"."isbn" = ?'
        query = _make_query(sql=sql, normalized_sql=norm, tables=[_BOOK_TABLE])
        prescriptions = self.analyzer.analyze([query])
        isbn_prescriptions = [p for p in prescriptions if "isbn" in p.description]
        assert len(isbn_prescriptions) == 0

    @pytest.mark.django_db
    def test_severity_is_info(self) -> None:
        """Missing index prescriptions should have INFO severity."""
        sql = 'SELECT * FROM "testapp_book" WHERE "testapp_book"."published_date" = ?'
        norm = 'select * from "testapp_book" where "testapp_book"."published_date" = ?'
        query = _make_query(sql=sql, normalized_sql=norm, tables=[_BOOK_TABLE])
        prescriptions = self.analyzer.analyze([query])
        assert len(prescriptions) >= 1
        assert prescriptions[0].severity == Severity.INFO

    @pytest.mark.django_db
    def test_non_select_queries_ignored(self) -> None:
        """Non-SELECT queries should be ignored."""
        sql = 'UPDATE "testapp_book" SET "title" = \'New\' WHERE "published_date" = \'2024-01-01\''
        norm = 'update "testapp_book" set "title" = ? where "published_date" = ?'
        query = CapturedQuery(
            sql=sql,
            params=None,
            duration_ms=1.0,
            fingerprint="abc123",
            normalized_sql=norm,
            callsite=None,
            is_select=False,
            tables=[_BOOK_TABLE],
        )
        prescriptions = self.analyzer.analyze([query])
        assert len(prescriptions) == 0

    def test_empty_queries(self) -> None:
        """Empty query list should return no prescriptions."""
        prescriptions = self.analyzer.analyze([])
        assert prescriptions == []

    @pytest.mark.django_db
    def test_unknown_table_handled_gracefully(self) -> None:
        """Queries referencing unknown tables should not crash."""
        sql = 'SELECT * FROM "nonexistent_table" WHERE "nonexistent_table"."foo" = ?'
        norm = 'select * from "nonexistent_table" where "nonexistent_table"."foo" = ?'
        query = _make_query(sql=sql, normalized_sql=norm, tables=["nonexistent_table"])
        prescriptions = self.analyzer.analyze([query])
        assert isinstance(prescriptions, list)

    @pytest.mark.django_db
    def test_composite_filter_pattern(self) -> None:
        """Two non-indexed fields filtered together should be detected."""
        sql = (
            'SELECT * FROM "testapp_book" '
            'WHERE "testapp_book"."published_date" = ? '
            'AND "testapp_book"."price" = ?'
        )
        norm = (
            'select * from "testapp_book" '
            'where "testapp_book"."published_date" = ? '
            'and "testapp_book"."price" = ?'
        )
        query = _make_query(sql=sql, normalized_sql=norm, tables=[_BOOK_TABLE])
        prescriptions = self.analyzer.analyze([query])
        assert len(prescriptions) >= 1

    @pytest.mark.django_db
    def test_analysis_exception_returns_empty(self) -> None:
        """If analysis crashes internally, return empty list."""
        sql = 'SELECT * FROM "testapp_book" WHERE "testapp_book"."published_date" = ?'
        norm = 'select * from "testapp_book" where "testapp_book"."published_date" = ?'
        query = _make_query(sql=sql, normalized_sql=norm, tables=[_BOOK_TABLE])
        original = self.analyzer._detect_missing_indexes
        self.analyzer._detect_missing_indexes = lambda q: (_ for _ in ()).throw(  # type: ignore[assignment]
            RuntimeError("boom")
        )
        try:
            prescriptions = self.analyzer.analyze([query])
            assert prescriptions == []
        finally:
            self.analyzer._detect_missing_indexes = original  # type: ignore[assignment]
