"""DRF serializer analyzer for detecting missing queryset optimizations.

Detects when a Django REST Framework ViewSet/APIView uses nested serializers
without corresponding select_related/prefetch_related on the queryset.
Generates prescriptions with the exact get_queryset() override needed.

Algorithm:
1. Inspect the serializer class for nested serializers or RelatedField subclasses.
2. For each nested relation, check if the view's queryset includes the
   corresponding select_related/prefetch_related.
3. If not, generate a Prescription with the exact fix.
"""

from __future__ import annotations

import logging
from typing import Any

from query_doctor.analyzers.base import BaseAnalyzer
from query_doctor.types import (
    CapturedQuery,
    IssueType,
    Prescription,
    Severity,
)

logger = logging.getLogger("query_doctor")


def _get_nested_relations(serializer_class: Any) -> list[dict[str, Any]]:
    """Inspect a DRF serializer for nested serializer fields.

    Returns a list of dicts with 'field_name' and 'relation_type' keys.
    relation_type is 'fk' for forward ForeignKey or 'm2m' for ManyToMany.
    """
    relations: list[dict[str, Any]] = []

    try:
        from rest_framework import serializers as drf_serializers

        # Get declared fields from the serializer
        fields = getattr(serializer_class, "_declared_fields", {})

        for field_name, field_obj in fields.items():
            if isinstance(field_obj, drf_serializers.BaseSerializer):
                # It's a nested serializer — determine relation type
                relation_type = _determine_relation_type(serializer_class, field_name)
                relations.append(
                    {
                        "field_name": field_name,
                        "relation_type": relation_type,
                    }
                )
    except Exception:
        logger.debug("query_doctor: failed to inspect serializer fields", exc_info=True)

    return relations


def _determine_relation_type(serializer_class: Any, field_name: str) -> str:
    """Determine if a serializer field represents a FK or M2M relation.

    Returns 'fk' for ForeignKey/OneToOne, 'm2m' for ManyToMany/reverse FK.
    """
    try:
        model = getattr(getattr(serializer_class, "Meta", None), "model", None)
        if model is None:
            return "fk"

        field = model._meta.get_field(field_name)

        from django.db.models import ForeignKey, OneToOneField

        if isinstance(field, (ForeignKey, OneToOneField)):
            return "fk"

        from django.db.models import ManyToManyField, ManyToManyRel, ManyToOneRel

        if isinstance(field, (ManyToManyField, ManyToManyRel, ManyToOneRel)):
            return "m2m"
    except Exception:
        logger.debug("query_doctor: failed to determine relation type for %s", field_name)

    return "fk"


def _queryset_has_optimization(queryset: Any, field_name: str) -> bool:
    """Check if a queryset already includes select_related/prefetch_related for a field."""
    try:
        # Check select_related
        select_related = getattr(queryset.query, "select_related", None)
        if isinstance(select_related, dict) and field_name in select_related:
            return True
        if select_related is True:
            return True

        # Check prefetch lookups
        prefetch_lookups = getattr(queryset, "_prefetch_related_lookups", ())
        for lookup in prefetch_lookups:
            lookup_name = getattr(lookup, "prefetch_through", str(lookup))
            if lookup_name == field_name:
                return True
    except Exception:
        pass

    return False


class DRFSerializerAnalyzer(BaseAnalyzer):
    """Analyzer that detects DRF views missing queryset optimizations.

    Inspects DRF serializer classes for nested serializers and checks
    whether the corresponding queryset uses select_related or
    prefetch_related for those relations.
    """

    name: str = "drf_serializer"

    def analyze(
        self,
        queries: list[CapturedQuery],
        models_meta: dict[str, Any] | None = None,
    ) -> list[Prescription]:
        """Analyze captured queries for DRF serializer issues.

        Note: This analyzer primarily works through analyze_view() which
        is called with DRF-specific context. The query-based analyze()
        method serves as a fallback interface.

        Args:
            queries: List of captured queries to analyze.
            models_meta: Optional model metadata.

        Returns:
            List of prescriptions (empty for query-only analysis).
        """
        if not self.is_enabled():
            return []
        return []

    def analyze_view(
        self,
        view_class: Any = None,
        serializer_class: Any = None,
        queryset: Any = None,
    ) -> list[Prescription]:
        """Analyze a DRF view for missing queryset optimizations.

        Args:
            view_class: The DRF ViewSet or APIView class.
            serializer_class: The serializer class used by the view.
            queryset: The queryset used by the view.

        Returns:
            List of prescriptions for detected issues.
        """
        if not self.is_enabled() or serializer_class is None or queryset is None:
            return []

        try:
            return self._detect_missing_optimizations(view_class, serializer_class, queryset)
        except Exception:
            logger.warning("query_doctor: DRF serializer analysis failed", exc_info=True)
            return []

    def _detect_missing_optimizations(
        self,
        view_class: Any,
        serializer_class: Any,
        queryset: Any,
    ) -> list[Prescription]:
        """Core detection logic for missing queryset optimizations."""
        prescriptions: list[Prescription] = []
        nested_relations = _get_nested_relations(serializer_class)

        for relation in nested_relations:
            field_name = relation["field_name"]
            relation_type = relation["relation_type"]

            if _queryset_has_optimization(queryset, field_name):
                continue

            strategy = "select_related" if relation_type == "fk" else "prefetch_related"
            view_name = view_class.__name__ if view_class else "ViewSet"
            model_name = getattr(getattr(serializer_class, "Meta", None), "model", None)
            model_label = model_name.__name__ if model_name else "Model"

            prescriptions.append(
                Prescription(
                    issue_type=IssueType.DRF_SERIALIZER,
                    severity=Severity.WARNING,
                    description=(
                        f"DRF {view_name} uses nested serializer for "
                        f'"{field_name}" without {strategy}'
                    ),
                    fix_suggestion=(
                        f"Add .{strategy}('{field_name}') to the queryset in "
                        f"{view_name}.get_queryset(), e.g.:\n"
                        f"    def get_queryset(self):\n"
                        f"        return {model_label}.objects"
                        f".{strategy}('{field_name}').all()"
                    ),
                    callsite=None,
                    query_count=0,
                    extra={
                        "field": field_name,
                        "strategy": strategy,
                        "view": view_name,
                    },
                )
            )

        return prescriptions
