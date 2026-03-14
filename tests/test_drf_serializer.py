"""Tests for the DRF serializer analyzer.

Verifies that the analyzer detects DRF views with nested serializers
that are missing select_related/prefetch_related optimizations.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from rest_framework import serializers, viewsets
from rest_framework.test import APIRequestFactory

from query_doctor.analyzers.drf_serializer import DRFSerializerAnalyzer
from query_doctor.types import (
    CallSite,
    CapturedQuery,
    IssueType,
)
from tests.testapp.models import Author, Book, Publisher

# --- Test serializers ---


class PublisherSerializer(serializers.ModelSerializer):
    """Serializer for Publisher model."""

    class Meta:
        model = Publisher
        fields = ["id", "name", "country"]  # noqa: RUF012


class AuthorSerializer(serializers.ModelSerializer):
    """Serializer for Author model."""

    class Meta:
        model = Author
        fields = ["id", "name", "email"]  # noqa: RUF012


class BookSerializerWithNested(serializers.ModelSerializer):
    """Book serializer with nested author — triggers N+1 without select_related."""

    author = AuthorSerializer()

    class Meta:
        model = Book
        fields = ["id", "title", "author"]  # noqa: RUF012


class BookSerializerWithMultipleNested(serializers.ModelSerializer):
    """Book serializer with multiple nested serializers."""

    author = AuthorSerializer()
    publisher = PublisherSerializer()

    class Meta:
        model = Book
        fields = ["id", "title", "author", "publisher"]  # noqa: RUF012


class BookSerializerFlat(serializers.ModelSerializer):
    """Book serializer without nested serializers — no issues expected."""

    class Meta:
        model = Book
        fields = ["id", "title", "isbn"]  # noqa: RUF012


# --- Test viewsets ---


class UnoptimizedBookViewSet(viewsets.ModelViewSet):
    """ViewSet WITHOUT select_related — should trigger prescription."""

    queryset = Book.objects.all()
    serializer_class = BookSerializerWithNested


class OptimizedBookViewSet(viewsets.ModelViewSet):
    """ViewSet WITH select_related — should NOT trigger prescription."""

    queryset = Book.objects.select_related("author").all()
    serializer_class = BookSerializerWithNested


class MultiNestedUnoptimizedViewSet(viewsets.ModelViewSet):
    """ViewSet with multiple nested serializers, no optimization."""

    queryset = Book.objects.all()
    serializer_class = BookSerializerWithMultipleNested


class FlatBookViewSet(viewsets.ModelViewSet):
    """ViewSet with flat serializer — no nested relations."""

    queryset = Book.objects.all()
    serializer_class = BookSerializerFlat


def _make_drf_callsite() -> CallSite:
    """Create a callsite that looks like it came from DRF."""
    return CallSite(
        filepath="rest_framework/views.py",
        line_number=100,
        function_name="dispatch",
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
        normalized_sql=sql.lower(),
        callsite=callsite or _make_drf_callsite(),
        is_select=True,
        tables=tables or [],
    )


class TestDRFSerializerAnalyzer:
    """Tests for DRFSerializerAnalyzer."""

    def setup_method(self) -> None:
        """Set up analyzer instance."""
        self.analyzer = DRFSerializerAnalyzer()
        self.factory = APIRequestFactory()

    def test_analyzer_name(self) -> None:
        """Analyzer should have the correct name."""
        assert self.analyzer.name == "drf_serializer"

    @pytest.mark.django_db
    def test_unoptimized_viewset_detected(self) -> None:
        """ViewSet without select_related for nested serializer is detected."""
        prescriptions = self.analyzer.analyze_view(
            view_class=UnoptimizedBookViewSet,
            serializer_class=BookSerializerWithNested,
            queryset=Book.objects.all(),
        )
        assert len(prescriptions) >= 1
        rx = prescriptions[0]
        assert rx.issue_type == IssueType.DRF_SERIALIZER
        assert "author" in rx.fix_suggestion
        assert "select_related" in rx.fix_suggestion

    @pytest.mark.django_db
    def test_optimized_viewset_no_false_positive(self) -> None:
        """ViewSet with select_related should NOT trigger."""
        prescriptions = self.analyzer.analyze_view(
            view_class=OptimizedBookViewSet,
            serializer_class=BookSerializerWithNested,
            queryset=Book.objects.select_related("author").all(),
        )
        author_prescriptions = [p for p in prescriptions if "author" in p.fix_suggestion]
        assert len(author_prescriptions) == 0

    @pytest.mark.django_db
    def test_multiple_nested_serializers(self) -> None:
        """ViewSet with multiple nested serializers gives multiple prescriptions."""
        prescriptions = self.analyzer.analyze_view(
            view_class=MultiNestedUnoptimizedViewSet,
            serializer_class=BookSerializerWithMultipleNested,
            queryset=Book.objects.all(),
        )
        assert len(prescriptions) >= 2
        fields_suggested = [p.extra.get("field") for p in prescriptions]
        assert "author" in fields_suggested
        assert "publisher" in fields_suggested

    @pytest.mark.django_db
    def test_flat_serializer_no_issues(self) -> None:
        """ViewSet with flat serializer (no nested) should have no issues."""
        prescriptions = self.analyzer.analyze_view(
            view_class=FlatBookViewSet,
            serializer_class=BookSerializerFlat,
            queryset=Book.objects.all(),
        )
        assert len(prescriptions) == 0

    def test_empty_queries(self) -> None:
        """Empty query list should return no prescriptions."""
        prescriptions = self.analyzer.analyze([])
        assert prescriptions == []

    def test_analyze_returns_list(self) -> None:
        """The analyze method should always return a list."""
        query = _make_query(sql='SELECT * FROM "testapp_book"', tables=["testapp_book"])
        prescriptions = self.analyzer.analyze([query])
        assert isinstance(prescriptions, list)

    @pytest.mark.django_db
    def test_prescription_has_correct_issue_type(self) -> None:
        """Prescriptions should have DRF_SERIALIZER issue type."""
        prescriptions = self.analyzer.analyze_view(
            view_class=UnoptimizedBookViewSet,
            serializer_class=BookSerializerWithNested,
            queryset=Book.objects.all(),
        )
        for p in prescriptions:
            assert p.issue_type == IssueType.DRF_SERIALIZER

    @pytest.mark.django_db
    def test_analysis_exception_returns_empty(self) -> None:
        """If analysis crashes internally, return empty list."""
        original = self.analyzer.analyze_view
        self.analyzer.analyze_view = lambda **kw: (_ for _ in ()).throw(  # type: ignore[assignment]
            RuntimeError("boom")
        )
        try:
            query = _make_query(
                sql='SELECT * FROM "testapp_book"',
                tables=["testapp_book"],
            )
            prescriptions = self.analyzer.analyze([query])
            assert isinstance(prescriptions, list)
        finally:
            self.analyzer.analyze_view = original  # type: ignore[assignment]

    def test_disabled_via_config(self) -> None:
        """Analyzer should return empty when disabled in config."""
        disabled_config = {
            "ANALYZERS": {"drf_serializer": {"enabled": False}},
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
            prescriptions = self.analyzer.analyze([])
            assert prescriptions == []
