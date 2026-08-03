"""Tests for the AST-based SerializerMethodField N+1 analyzer.

Test serializer classes are defined inline -- no real Django models needed
since the analyzer reads source code statically via ast.parse().
"""

from __future__ import annotations

import pytest

# Only run if DRF is installed
drf = pytest.importorskip("rest_framework")

from rest_framework import serializers  # noqa: E402

from query_doctor.analyzers.serializer_method import SerializerMethodAnalyzer  # noqa: E402
from query_doctor.types import IssueType, Severity  # noqa: E402
from tests.testapp.models import Book  # noqa: E402

# ---------------------------------------------------------------------------
# Test serializer classes defined inline
# ---------------------------------------------------------------------------


class GoodSerializer(serializers.Serializer):
    """No SerializerMethodField -- should produce 0 prescriptions."""

    name = serializers.CharField()


class SafeSerializer(serializers.Serializer):
    """Methods that should NOT trigger warnings."""

    computed = serializers.SerializerMethodField()

    def get_computed(self, obj):
        """Safe: string operation, not DB access."""
        return obj.name.upper()


class BadCountSerializer(serializers.Serializer):
    """Pattern 1: Related manager access -- obj.items.count()."""

    total = serializers.SerializerMethodField()

    def get_total(self, obj):
        return obj.items.count()


class BadFilterSerializer(serializers.Serializer):
    """Pattern 2: Model.objects.filter() inside method."""

    recent = serializers.SerializerMethodField()

    def get_recent(self, obj):
        from django.contrib.auth.models import User

        return User.objects.filter(id=obj.id).count()


class BadChainSerializer(serializers.ModelSerializer):
    """Pattern 3: Deep attribute chain -- obj.author.name.

    A ``ModelSerializer``, unlike the other fixtures here, because the
    deep-chain site prescribes ``select_related`` and that needs the model to
    confirm ``author`` is a forward FK. With no model there is nothing to
    check the kind against and the site suppresses -- see
    :class:`TestDeepChainPrescribesOnlySelectRelatableFields`.
    """

    author_name = serializers.SerializerMethodField()

    class Meta:
        model = Book
        fields = ("author_name",)

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
        assert all(r.issue_type == IssueType.SERIALIZER_METHOD_FIELD for r in results)

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


class TestSerializerMethodConfigToggle:
    """Tests that ANALYZERS.serializer_method.enabled actually gates analyze_serializer().

    Prior to this, DEFAULT_CONFIG had no serializer_method key, so is_enabled()
    always fell back to True with no key for a user to override -- the toggle
    was unreachable. BadCountSerializer is a real finding-producing fixture (it
    is already proven to trigger a prescription above), so the disabled case
    below isn't passing "for free" on empty input.
    """

    def test_disabled_via_config_produces_no_findings(self) -> None:
        from django.test import override_settings

        from query_doctor.conf import get_config

        with override_settings(
            QUERY_DOCTOR={"ANALYZERS": {"serializer_method": {"enabled": False}}}
        ):
            get_config.cache_clear()
            analyzer = SerializerMethodAnalyzer()
            results = analyzer.analyze_serializer(BadCountSerializer)
            get_config.cache_clear()

        assert results == []

    def test_enabled_via_config_positive_control(self) -> None:
        from django.test import override_settings

        from query_doctor.conf import get_config

        with override_settings(
            QUERY_DOCTOR={"ANALYZERS": {"serializer_method": {"enabled": True}}}
        ):
            get_config.cache_clear()
            analyzer = SerializerMethodAnalyzer()
            results = analyzer.analyze_serializer(BadCountSerializer)
            get_config.cache_clear()

        assert len(results) >= 1


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


class TestLoopOverScalarAttribute:
    """Entry 50: a loop over a scalar attribute must not prescribe prefetching.

    ``for ch in obj.title`` iterates a string. ``prefetch_related('title')``
    raises ``ValueError: 'title' does not resolve to an item that supports
    prefetching``, so the bare-attribute loop branch has to establish that the
    attribute really is a relation before it names it.
    """

    def setup_method(self):
        """Create analyzer instance."""
        self.analyzer = SerializerMethodAnalyzer()

    def test_loop_over_charfield_on_model_serializer_is_not_flagged(self):
        """The model says `title` is a CharField, so there is nothing to prefetch."""
        from tests.testapp.models import Book

        class BookTitleSerializer(serializers.ModelSerializer):
            n = serializers.SerializerMethodField()

            class Meta:
                model = Book
                fields = ("n",)

            def get_n(self, obj):
                total = 0
                for _ch in obj.title:
                    total += 1
                return total

        results = self.analyzer.analyze_serializer(BookTitleSerializer)
        loop_results = [r for r in results if r.extra.get("pattern") == "loop_queryset"]
        assert loop_results == []

    def test_loop_over_relation_on_model_serializer_is_flagged(self):
        """Positive control: the same shape over a real relation still fires."""
        from tests.testapp.models import Book

        class BookCategoriesSerializer(serializers.ModelSerializer):
            n = serializers.SerializerMethodField()

            class Meta:
                model = Book
                fields = ("n",)

            def get_n(self, obj):
                total = 0
                for _cat in obj.categories:
                    total += 1
                return total

        results = self.analyzer.analyze_serializer(BookCategoriesSerializer)
        loop_results = [r for r in results if r.extra.get("pattern") == "loop_queryset"]
        assert len(loop_results) == 1
        assert "prefetch_related('categories')" in loop_results[0].fix_suggestion

    def test_loop_over_unknown_attribute_without_a_model_is_not_flagged(self):
        """With no `Meta.model` there is nothing to validate against.

        A plain `Serializer` gives the analyzer no way to tell a relation from
        a string, and naming a guess is what entry 50 is about.
        """

        class PlainSerializer(serializers.Serializer):
            n = serializers.SerializerMethodField()

            def get_n(self, obj):
                total = 0
                for _ch in obj.title:
                    total += 1
                return total

        results = self.analyzer.analyze_serializer(PlainSerializer)
        loop_results = [r for r in results if r.extra.get("pattern") == "loop_queryset"]
        assert loop_results == []

    def test_loop_over_default_reverse_accessor_is_flagged(self):
        """Positive control without a model: `_set` is Django's own accessor name."""

        class PlainSetSerializer(serializers.Serializer):
            n = serializers.SerializerMethodField()

            def get_n(self, obj):
                total = 0
                for _item in obj.review_set:
                    total += 1
                return total

        results = self.analyzer.analyze_serializer(PlainSetSerializer)
        loop_results = [r for r in results if r.extra.get("pattern") == "loop_queryset"]
        assert len(loop_results) == 1
        assert "prefetch_related('review_set')" in loop_results[0].fix_suggestion


class TestDeepChainPrescribesOnlySelectRelatableFields:
    """B5 site 7: `select_related` needs relation *kind*, not relation existence.

    ``_check_deep_chain`` prescribes ``select_related(chain[1])`` for any
    three-deep attribute access. ``is_relation`` is true for reverse and
    many-to-many descriptors too, and ``select_related`` rejects both, so the
    guard the loop branch uses is not the guard this site needs:

        Book.objects.select_related('categories')
            -> FieldError: Invalid field name(s) given in select_related:
               'categories'. Choices are: author, publisher

    Django's default reverse accessor suffix is the same story. It is a
    prefetch signal, and site 7 does not prescribe prefetching.
    """

    def setup_method(self):
        """Create analyzer instance."""
        self.analyzer = SerializerMethodAnalyzer()

    @staticmethod
    def _chain_findings(analyzer, serializer_cls):
        """Return only this site's findings."""
        return [
            r
            for r in analyzer.analyze_serializer(serializer_cls)
            if r.extra.get("pattern") == "deep_attribute_chain"
        ]

    def test_forward_fk_is_still_prescribed(self):
        """Positive control: the case select_related actually fixes."""
        from tests.testapp.models import Book

        class S(serializers.ModelSerializer):
            n = serializers.SerializerMethodField()

            class Meta:
                model = Book
                fields = ("n",)

            def get_n(self, obj):
                return obj.author.name

        found = self._chain_findings(self.analyzer, S)
        assert len(found) == 1, found
        assert "select_related('author')" in found[0].fix_suggestion

    def test_many_to_many_is_not_prescribed(self):
        """`is_relation` admits it; select_related raises on it."""
        from tests.testapp.models import Book

        class S(serializers.ModelSerializer):
            n = serializers.SerializerMethodField()

            class Meta:
                model = Book
                fields = ("n",)

            def get_n(self, obj):
                return obj.categories.name

        assert self._chain_findings(self.analyzer, S) == []

    def test_non_relation_is_not_prescribed(self):
        """A CharField chain: the original B5 symptom at this site."""
        from tests.testapp.models import Book

        class S(serializers.ModelSerializer):
            n = serializers.SerializerMethodField()

            class Meta:
                model = Book
                fields = ("n",)

            # A terminal attribute, not a method: `upper` is in _SAFE_METHODS
            # and `count` in _QUERYSET_METHODS, and either would make this
            # pass at an earlier guard than the one under test.
            def get_n(self, obj):
                return obj.title.length

        assert self._chain_findings(self.analyzer, S) == []

    def test_reverse_accessor_is_not_prescribed_without_a_model(self):
        """The `_set` branch is a prefetch signal, so it must not reach here."""

        class S(serializers.Serializer):
            n = serializers.SerializerMethodField()

            def get_n(self, obj):
                return obj.review_set.headline

        assert self._chain_findings(self.analyzer, S) == []

    def test_an_unresolvable_attribute_is_not_prescribed(self):
        """No model to consult and no structural signal: suppress."""

        class S(serializers.Serializer):
            n = serializers.SerializerMethodField()

            def get_n(self, obj):
                return obj.payload.theme

        assert self._chain_findings(self.analyzer, S) == []

    def test_the_resolver_never_renames_on_either_arm(self):
        """Baseline keys embed the name, so resolution must not rewrite it.

        `baseline.py` keys an issue on ``analyzer:file_path:message`` and every
        one of these descriptions interpolates the resolved name. A resolver
        that returned an accessor name instead of the source token would
        silently rekey every stored entry.
        """
        from tests.testapp.models import Book

        class S(serializers.ModelSerializer):
            n = serializers.SerializerMethodField()

            class Meta:
                model = Book
                fields = ("n",)

            def get_n(self, obj):
                return obj.author.name

        for attr in ("author", "publisher", "categories", "title", "nope"):
            for cls in (S, serializers.Serializer):
                assert SerializerMethodAnalyzer._resolve_relation_name(cls, attr) in (attr, None)
                assert SerializerMethodAnalyzer._resolve_select_related_name(cls, attr) in (
                    attr,
                    None,
                )
