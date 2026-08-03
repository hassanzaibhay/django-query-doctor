"""Tests for the missing index analyzer.

Verifies that the analyzer correctly detects queries filtering or ordering
on non-indexed columns and suggests adding Meta.indexes with models.Index().
"""

from __future__ import annotations

from typing import Any, ClassVar

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


def _index_from(fix_suggestion: str) -> Any:
    """Build the ``models.Index`` the prescription literally tells the user to add.

    The emitted string *is* the input under test, so it is evaluated rather
    than pattern-matched. A regex over the name would have stayed green while
    the suggestion was unusable: the defect was never in the shape of the
    text, it was in a length Django rejects.
    """
    from django.db import models

    start = fix_suggestion.index("[models.Index(")
    expr = fix_suggestion[start:]
    indexes = eval(expr, {"models": models})
    assert len(indexes) == 1, indexes
    return indexes[0]


class TestPrescribedIndexIsAcceptedByDjango:
    """Django must accept the index the prescription tells the user to paste.

    ``Index.max_name_length`` is 30 and ``Model._check_indexes`` enforces it
    for every configured database with no backend gate, so an over-long name
    is a hard `models.E034` at ``manage.py check`` time -- the user's project
    stops passing checks because they followed our advice.
    """

    def setup_method(self) -> None:
        """Set up analyzer instance."""
        self.analyzer = MissingIndexAnalyzer()

    def _emitted_index(self, table: str, column: str, model: Any) -> Any:
        """Return the ``models.Index`` the prescription tells the user to paste."""
        rx = self.analyzer._build_prescription(table, column, model, _make_query("SELECT 1"))
        return _index_from(rx.fix_suggestion)

    @pytest.mark.django_db
    def test_django_accepts_the_emitted_index(self) -> None:
        """Declare the emitted index on a real model and run Django's checks.

        This is the assertion the old tests lacked: they asserted
        ``"Meta.indexes" in fix_suggestion``, which any string containing that
        substring satisfies. Here Django itself is the judge, so the test
        cannot pass while the advice is unusable.

        ``isolate_apps`` is required rather than convenient: a model really
        registered under ``testapp`` would be found by
        ``_get_model_for_table``'s ``apps.get_models()`` scan and perturb the
        other tests in this file.
        """
        from django.apps import apps
        from django.db import models
        from django.test.utils import isolate_apps

        source = apps.get_model("testapp", "Book")
        emitted = self._emitted_index("testapp_book", "published_date", source)

        with isolate_apps("tests.testapp"):

            class IndexProbe(models.Model):
                published_date = models.DateField(null=True)

                class Meta:
                    app_label = "testapp"
                    indexes: ClassVar[list[Any]] = [emitted]

            errors = IndexProbe.check(databases=["default"])

        codes = [e.id for e in errors]
        assert "models.E034" not in codes, [str(e) for e in errors]
        assert errors == [], [str(e) for e in errors]

    @pytest.mark.django_db
    def test_the_suggestion_names_no_index(self) -> None:
        """Django auto-names, which removes the length class rather than capping it.

        ``set_name_with_model`` builds ``table[:11]_column[:7]_<hash>_idx``,
        which is bounded under 30 by construction and hashed over the table
        and columns, so it is collision-safe in a way a truncation is not.
        """
        from django.apps import apps

        model = apps.get_model("testapp", "Book")
        rx = self.analyzer._build_prescription(
            "testapp_book", "published_date", model, _make_query("SELECT 1")
        )
        assert "name=" not in rx.fix_suggestion, rx.fix_suggestion


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
        assert "Meta.indexes" in rx.fix_suggestion

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
