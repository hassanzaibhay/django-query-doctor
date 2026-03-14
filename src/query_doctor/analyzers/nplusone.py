"""N+1 query detection analyzer.

Detects N+1 query patterns by grouping captured queries by fingerprint
and checking for repeated SELECT queries that indicate missing
select_related() or prefetch_related() calls.

Algorithm:
1. Group queries by fingerprint
2. For each group with count >= threshold:
   a. Check if it's a SELECT query with a WHERE clause
   b. Determine if it's a PK lookup (FK) or a through-table lookup (M2M)
   c. Use Django _meta to find the relationship field name
3. Generate Prescription with exact fix suggestion
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Any

from query_doctor.analyzers.base import BaseAnalyzer
from query_doctor.conf import get_config
from query_doctor.types import (
    CapturedQuery,
    IssueType,
    Prescription,
    Severity,
)

logger = logging.getLogger("query_doctor")

# Matches WHERE "table"."id" = ? (PK lookup — FK N+1 access)
_PK_LOOKUP_RE = re.compile(
    r'where\s+"?(\w+)"?\."?id"?\s*=\s*\?',
    re.IGNORECASE,
)

# Matches WHERE "table"."something_id" = ? (FK column lookup — M2M or reverse FK)
_FK_COL_LOOKUP_RE = re.compile(
    r'where\s+"?(\w+)"?\."?(\w+_id)"?\s*=\s*\?',
    re.IGNORECASE,
)

# Extract the first table in FROM clause
_FROM_TABLE_RE = re.compile(
    r'from\s+"?(\w+)"?',
    re.IGNORECASE,
)


def _get_model_for_table(table_name: str) -> Any | None:
    """Look up a Django model class by its database table name."""
    try:
        from django.apps import apps

        for model in apps.get_models():
            if model._meta.db_table == table_name:
                return model
    except Exception:
        pass
    return None


def _is_through_table(table_name: str) -> dict[str, Any] | None:
    """Check if a table is a M2M through table.

    Returns info dict with field_name and parent_model if it is,
    None otherwise.
    """
    try:
        from django.apps import apps

        for model in apps.get_models():
            for field in model._meta.get_fields():
                if hasattr(field, "m2m_db_table") and field.m2m_db_table() == table_name:
                    return {
                        "field_name": field.name,
                        "parent_model": model,
                    }
    except Exception:
        logger.debug("query_doctor: failed to check through table", exc_info=True)
    return None


def _find_fk_field_names(target_table: str) -> list[str]:
    """Find FK field names on other models that point to target_table's model."""
    try:
        target_model = _get_model_for_table(target_table)
        if target_model is None:
            return []

        from django.apps import apps

        names = []
        for model in apps.get_models():
            for field in model._meta.get_fields():
                if (
                    hasattr(field, "related_model")
                    and hasattr(field, "column")
                    and hasattr(field, "name")
                    and field.related_model == target_model
                ):
                    names.append(field.name)
        return names
    except Exception:
        return []


class NPlusOneAnalyzer(BaseAnalyzer):
    """Analyzer that detects N+1 query patterns.

    Groups queries by fingerprint and identifies repeated SELECT queries
    that indicate missing select_related() or prefetch_related() calls.
    """

    name: str = "nplusone"

    def analyze(
        self,
        queries: list[CapturedQuery],
        models_meta: dict[str, Any] | None = None,
    ) -> list[Prescription]:
        """Analyze queries for N+1 patterns.

        Args:
            queries: List of captured queries to analyze.
            models_meta: Optional model metadata (not used currently).

        Returns:
            List of prescriptions for detected N+1 issues.
        """
        if not queries:
            return []

        try:
            return self._detect_nplusone(queries)
        except Exception:
            logger.warning("query_doctor: N+1 analysis failed", exc_info=True)
            return []

    def _detect_nplusone(self, queries: list[CapturedQuery]) -> list[Prescription]:
        """Core N+1 detection logic."""
        config = get_config()
        threshold = config["ANALYZERS"]["nplusone"].get("threshold", 3)

        # Group SELECT queries by fingerprint
        groups: dict[str, list[CapturedQuery]] = defaultdict(list)
        for q in queries:
            if q.is_select:
                groups[q.fingerprint].append(q)

        prescriptions: list[Prescription] = []

        for fp, group in groups.items():
            if len(group) < threshold:
                continue

            sample = group[0]
            normalized = sample.normalized_sql

            prescription = self._classify_and_prescribe(group, normalized, fp)
            if prescription:
                prescriptions.append(prescription)

        return prescriptions

    def _classify_and_prescribe(
        self,
        group: list[CapturedQuery],
        normalized: str,
        fp: str,
    ) -> Prescription | None:
        """Classify the N+1 pattern and build a prescription."""
        # First check: WHERE "table"."something_id" = ?
        # This could be a M2M through-table access or reverse FK
        fk_col_match = _FK_COL_LOOKUP_RE.search(normalized)
        if fk_col_match:
            where_table = fk_col_match.group(1)
            fk_column = fk_col_match.group(2)

            # Check if the WHERE table is a through table → M2M
            through_info = _is_through_table(where_table)
            if through_info:
                return self._build_prescription(
                    group=group,
                    table=where_table,
                    field_name=through_info["field_name"],
                    strategy="prefetch_related",
                    fp=fp,
                )

            # Also check: the FROM table might use a through table
            # (queries JOIN through_table WHERE through_table.fk_id = ?)
            from_match = _FROM_TABLE_RE.search(normalized)
            if from_match:
                from_table = from_match.group(1)
                if from_table != where_table:
                    # The query JOINs from_table with where_table
                    through_info = _is_through_table(where_table)
                    if through_info:
                        return self._build_prescription(
                            group=group,
                            table=where_table,
                            field_name=through_info["field_name"],
                            strategy="prefetch_related",
                            fp=fp,
                        )

            # It's a regular FK-column lookup (reverse FK)
            field_name = fk_column.removesuffix("_id")
            return self._build_prescription(
                group=group,
                table=where_table,
                field_name=field_name,
                strategy="prefetch_related",
                fp=fp,
            )

        # Second check: WHERE "table"."id" = ? (PK lookup — forward FK)
        pk_match = _PK_LOOKUP_RE.search(normalized)
        if pk_match:
            target_table = pk_match.group(1)
            fk_names = _find_fk_field_names(target_table)
            field_name = (
                fk_names[0]
                if fk_names
                else (target_table.split("_", 1)[-1] if "_" in target_table else target_table)
            )
            return self._build_prescription(
                group=group,
                table=target_table,
                field_name=field_name,
                strategy="select_related",
                fp=fp,
            )

        return None

    def _build_prescription(
        self,
        group: list[CapturedQuery],
        table: str,
        field_name: str,
        strategy: str,
        fp: str,
    ) -> Prescription:
        """Build an N+1 prescription."""
        count = len(group)
        total_time = sum(q.duration_ms for q in group)
        severity = Severity.CRITICAL if count >= 10 else Severity.WARNING
        callsite = next((q.callsite for q in group if q.callsite), None)

        return Prescription(
            issue_type=IssueType.N_PLUS_ONE,
            severity=severity,
            description=(
                f'N+1 detected: {count} queries for table "{table}" (field: {field_name})'
            ),
            fix_suggestion=(f"Add .{strategy}('{field_name}') to your queryset"),
            callsite=callsite,
            query_count=count,
            time_saved_ms=total_time * (count - 1) / count if count > 0 else 0,
            fingerprint=fp,
            extra={"table": table, "field": field_name},
        )
