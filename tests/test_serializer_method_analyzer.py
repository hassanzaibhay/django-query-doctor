"""Tests for the AST-based SerializerMethodField N+1 analyzer.

Test serializer classes are defined inline — no real Django models needed
since the analyzer reads source code statically via ast.parse().
"""

from __future__ import annotations

import pytest

# Only run if DRF is installed
drf = pytest.importorskip("rest_framework")

from rest_framework import serializers  # noqa: E402

from query_doctor.analyzers.serializer_method import SerializerMethodAnalyzer  # noqa: E402
from query_doctor.types import IssueType, Severity  # noqa: E402

# ---------------------------------------------------------------------------
# Test serializer classes defined inline
# ---------------------------------------------------------------------------


class GoodSerializer(serializers.Serializer):
    """No SerializerMethodField — should produce 0 prescriptions."""

    name = serializers.CharField()


class SafeSerializer(serializers.Serializer):
    """Methods that should NOT trigger warnings."""

    computed = serializers.SerializerMethodField()

    def get_computed(self, obj):
        """Safe: string operation, not DB access."""
        return obj.name.upper()


class BadCountSerializer(serializers.Serializer):
    """Pattern 1: Related manager access — obj.items.count()."""

    total = serializers.SerializerMethodField()

    def get_total(self, obj):
        return obj.items.count()


class BadFilterSerializer(serializers.Serializer):
    """Pattern 2: Model.objects.filter() inside method."""

    recent = serializers.SerializerMethodField()

    def get_recent(self, obj):
        from django.contrib.auth.models import User

        return User.objects.filter(id=obj.id).count()


class BadChainSerializer(serializers.Serializer):
    """Pattern 3: Deep attribute chain — obj.author.name."""

    author_name = serializers.SerializerMethodField()

    def get_author_name(self, obj):
        return obj.author.name


class LoopSerializer(serializers.Serializer):
    """Pattern 4: For loop with queryset iteration."""

    items = serializers.SerializerMethodField()

    def get_items(self, obj):
        return [i.name for i in obj.related_set.all()]


class MultipleIssuesSerializer(serializers.Serializer):
    """Multiple SerializerMethodFields, some safe, some dangerous."""

    safe = serializers.SerializerMethodField()
    dangerous = serializers.SerializerMethodField()

    def get_safe(self, obj):
        return str(obj.id)

    def get_dangerous(self, obj):
        return obj.items.count()


class NoGetMethodSerializer(serializers.Serializer):
    """SerializerMethodField without corresponding get_ method."""

    missing = serializers.SerializerMethodField()


class ObjectsGetSerializer(serializers.Serializer):
    """Pattern 2 variant: Model.objects.get()."""

    profile = serializers.SerializerMethodField()

    def get_profile(self, obj):
        from django.contrib.auth.models import User

        return User.objects.get(id=obj.id)


class ExistsCheckSerializer(serializers.Serializer):
    """Pattern 1 variant: obj.related.exists()."""

    has_items = serializers.SerializerMethodField()

    def get_has_items(self, obj):
        return obj.items.exists()


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


class TestSerializerMethodAnalyzer:
    """Tests for the SerializerMethodAnalyzer."""

    def setup_method(self):
        """Create analyzer instance for each test."""
        self.analyzer = SerializerMethodAnalyzer()

    def test_no_method_fields(self):
        """Serializer without SerializerMethodField produces 0 prescriptions."""
        results = self.analyzer.analyze_serializer(GoodSerializer)
        assert len(results) == 0

    def test_safe_method_no_warning(self):
        """Safe string operation should not trigger warning."""
        results = self.analyzer.analyze_serializer(SafeSerializer)
        assert len(results) == 0

    def test_detects_related_manager_count(self):
        """Pattern 1: obj.items.count() should be detected."""
        results = self.analyzer.analyze_serializer(BadCountSerializer)
        assert len(results) >= 1
        assert any(
            "items" in r.description.lower() or "count" in r.description.lower() for r in results
        )
        assert all(r.issue_type == IssueType.DRF_SERIALIZER for r in results)

    def test_detects_objects_filter(self):
        """Pattern 2: Model.objects.filter() should be detected."""
        results = self.analyzer.analyze_serializer(BadFilterSerializer)
        assert len(results) >= 1
        assert any(
            "objects" in r.description.lower() or "filter" in r.description.lower()
            for r in results
        )

    def test_detects_deep_chain(self):
        """Pattern 3: obj.author.name should be detected."""
        results = self.analyzer.analyze_serializer(BadChainSerializer)
        assert len(results) >= 1
        assert any(
            "author" in r.description.lower() or "select_related" in r.fix_suggestion.lower()
            for r in results
        )

    def test_detects_loop_with_queryset(self):
        """Pattern 4: Loop over obj.related_set.all() should be detected."""
        results = self.analyzer.analyze_serializer(LoopSerializer)
        assert len(results) >= 1
        assert any(
            "loop" in r.description.lower() or "related_set" in r.description.lower()
            for r in results
        )

    def test_multiple_fields_mixed(self):
        """Only dangerous fields flagged, safe fields skipped."""
        results = self.analyzer.analyze_serializer(MultipleIssuesSerializer)
        # Only the dangerous field should produce prescriptions
        assert len(results) >= 1
        assert all(r.extra.get("field") == "dangerous" for r in results)

    def test_missing_get_method_skipped(self):
        """SerializerMethodField without get_<field> method is skipped gracefully."""
        results = self.analyzer.analyze_serializer(NoGetMethodSerializer)
        assert len(results) == 0

    def test_detects_objects_get(self):
        """Pattern 2 variant: Model.objects.get() should be detected."""
        results = self.analyzer.analyze_serializer(ObjectsGetSerializer)
        assert len(results) >= 1
        assert any("objects" in r.description.lower() for r in results)

    def test_detects_exists_check(self):
        """Pattern 1 variant: obj.items.exists() should be detected."""
        results = self.analyzer.analyze_serializer(ExistsCheckSerializer)
        assert len(results) >= 1

    def test_prescription_has_callsite(self):
        """Prescriptions include callsite with file path and line number."""
        results = self.analyzer.analyze_serializer(BadCountSerializer)
        assert len(results) >= 1
        for r in results:
            assert r.callsite is not None
            assert r.callsite.filepath != ""
            assert r.callsite.line_number > 0

    def test_prescription_has_extra_metadata(self):
        """Prescriptions include extra metadata (field, pattern, serializer)."""
        results = self.analyzer.analyze_serializer(BadCountSerializer)
        assert len(results) >= 1
        for r in results:
            assert "field" in r.extra
            assert "pattern" in r.extra
            assert "serializer" in r.extra
            assert r.extra["serializer"] == "BadCountSerializer"

    def test_severity_levels(self):
        """Related manager and queryset patterns are WARNING, deep chains are INFO."""
        # Related manager
        results = self.analyzer.analyze_serializer(BadCountSerializer)
        assert all(r.severity == Severity.WARNING for r in results)

        # Deep chain
        results = self.analyzer.analyze_serializer(BadChainSerializer)
        deep_chain_results = [
            r for r in results if r.extra.get("pattern") == "deep_attribute_chain"
        ]
        assert all(r.severity == Severity.INFO for r in deep_chain_results)

    def test_fix_suggestion_present(self):
        """All prescriptions have non-empty fix suggestions."""
        for cls in [BadCountSerializer, BadFilterSerializer, BadChainSerializer, LoopSerializer]:
            results = self.analyzer.analyze_serializer(cls)
            for r in results:
                assert r.fix_suggestion, f"Empty fix_suggestion for {cls.__name__}"


class TestSerializerMethodAnalyzerEdgeCases:
    """Edge case tests for the analyzer."""

    def setup_method(self):
        """Create analyzer instance."""
        self.analyzer = SerializerMethodAnalyzer()

    def test_empty_serializer(self):
        """Serializer with no fields at all."""

        class EmptySerializer(serializers.Serializer):
            pass

        results = self.analyzer.analyze_serializer(EmptySerializer)
        assert len(results) == 0

    def test_non_serializer_class(self):
        """Non-serializer class passed to analyzer."""

        class NotASerializer:
            pass

        # Should handle gracefully (no _declared_fields)
        results = self.analyzer.analyze_serializer(NotASerializer)
        assert len(results) == 0

    def test_method_on_parent_class(self):
        """Method defined on parent class should be found via MRO."""

        class ParentSerializer(serializers.Serializer):
            total = serializers.SerializerMethodField()

            def get_total(self, obj):
                return obj.items.count()

        class ChildSerializer(ParentSerializer):
            pass

        results = self.analyzer.analyze_serializer(ChildSerializer)
        assert len(results) >= 1

    def test_drf_not_installed_graceful(self):
        """If _find_method_fields is called without DRF, returns empty."""
        # The importorskip at module level handles this.
        # We test the analyzer itself handles non-DRF fields.
        analyzer = SerializerMethodAnalyzer()

        class FakeSerializer:
            _declared_fields = {"foo": "not a SerializerMethodField"}  # noqa: RUF012

        results = analyzer.analyze_serializer(FakeSerializer)
        assert len(results) == 0


class TestComprehensionDetection:
    """Tests for comprehension/generator N+1 detection (Pattern 5)."""

    def setup_method(self):
        """Create analyzer instance."""
        self.analyzer = SerializerMethodAnalyzer()

    def test_list_comprehension_with_queryset_call(self):
        """List comprehension iterating over obj.related.all() is detected."""

        class ListCompSerializer(serializers.Serializer):
            names = serializers.SerializerMethodField()

            def get_names(self, obj):
                return [item.name for item in obj.items.all()]

        results = self.analyzer.analyze_serializer(ListCompSerializer)
        comp_results = [r for r in results if r.extra.get("pattern") == "comprehension_queryset"]
        assert len(comp_results) >= 1
        assert "comprehension" in comp_results[0].description

    def test_generator_expression_with_queryset_call(self):
        """Generator expression iterating over obj.related.filter() is detected."""

        class GenExpSerializer(serializers.Serializer):
            ids = serializers.SerializerMethodField()

            def get_ids(self, obj):
                return list(x.id for x in obj.items.filter())

        results = self.analyzer.analyze_serializer(GenExpSerializer)
        comp_results = [r for r in results if r.extra.get("pattern") == "comprehension_queryset"]
        assert len(comp_results) >= 1

    def test_set_comprehension_with_queryset(self):
        """Set comprehension iterating over queryset is detected."""

        class SetCompSerializer(serializers.Serializer):
            unique_names = serializers.SerializerMethodField()

            def get_unique_names(self, obj):
                return {item.name for item in obj.tags.all()}

        results = self.analyzer.analyze_serializer(SetCompSerializer)
        comp_results = [r for r in results if r.extra.get("pattern") == "comprehension_queryset"]
        assert len(comp_results) >= 1

    def test_dict_comprehension_with_queryset(self):
        """Dict comprehension iterating over queryset is detected."""

        class DictCompSerializer(serializers.Serializer):
            mapping = serializers.SerializerMethodField()

            def get_mapping(self, obj):
                return {item.id: item.name for item in obj.items.all()}

        results = self.analyzer.analyze_serializer(DictCompSerializer)
        comp_results = [r for r in results if r.extra.get("pattern") == "comprehension_queryset"]
        assert len(comp_results) >= 1

    def test_comprehension_with_implicit_iteration(self):
        """Comprehension iterating over obj.related (no .all()) is detected."""

        class ImplicitCompSerializer(serializers.Serializer):
            vals = serializers.SerializerMethodField()

            def get_vals(self, obj):
                return [x for x in obj.items]

        results = self.analyzer.analyze_serializer(ImplicitCompSerializer)
        comp_results = [r for r in results if r.extra.get("pattern") == "comprehension_queryset"]
        assert len(comp_results) >= 1

    def test_safe_comprehension_not_flagged(self):
        """Comprehension over a local variable is not flagged."""

        class SafeCompSerializer(serializers.Serializer):
            doubled = serializers.SerializerMethodField()

            def get_doubled(self, obj):
                data = [1, 2, 3]
                return [x * 2 for x in data]

        results = self.analyzer.analyze_serializer(SafeCompSerializer)
        comp_results = [r for r in results if r.extra.get("pattern") == "comprehension_queryset"]
        assert len(comp_results) == 0

    def test_comprehension_severity_is_warning(self):
        """Comprehension queryset issues have WARNING severity."""

        class SevCompSerializer(serializers.Serializer):
            names = serializers.SerializerMethodField()

            def get_names(self, obj):
                return [item.name for item in obj.items.all()]

        results = self.analyzer.analyze_serializer(SevCompSerializer)
        comp_results = [r for r in results if r.extra.get("pattern") == "comprehension_queryset"]
        assert all(r.severity == Severity.WARNING for r in comp_results)
