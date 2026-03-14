"""Missing index detection analyzer.

Detects SELECT queries that filter (WHERE) or order (ORDER BY) on columns
that lack a database index, and generates prescriptions suggesting
db_index=True or Meta.indexes.

Algorithm:
1. For each SELECT query, extract WHERE and ORDER BY column references.
2. Map column names back to Django model fields via Model._meta.get_fields().
3. For each field, check if it has an index (db_index, unique, PK, FK, Meta.indexes).
4. If not indexed, generate a Prescription suggesting db_index=True.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from query_doctor.analyzers.base import BaseAnalyzer
from query_doctor.types import (
    CapturedQuery,
    IssueType,
    Prescription,
    Severity,
)

logger = logging.getLogger("query_doctor")

# Match WHERE "table"."column" = ? (and variations with AND/OR)
_WHERE_COL_RE = re.compile(
    r'"(\w+)"\."(\w+)"\s*(?:=|<|>|<=|>=|<>|!=|LIKE|IN|IS)\s',
    re.IGNORECASE,
)

# Match ORDER BY "table"."column"
_ORDER_BY_COL_RE = re.compile(
    r"ORDER\s+BY\s+(.+?)(?:\s+LIMIT|\s*$)",
    re.IGNORECASE,
)

# Match individual column refs in ORDER BY clause
_ORDER_COL_RE = re.compile(
    r'"(\w+)"\."(\w+)"',
)


def _get_model_for_table(table_name: str) -> Any | None:
    """Look up a Django model class by its database table name."""
    try:
        from django.apps import apps

        for model in apps.get_models():
            if model._meta.db_table == table_name:
                return model
    except Exception:
        logger.debug("query_doctor: failed model lookup for table %s", table_name)
    return None


def _field_is_indexed(model: Any, field_name: str) -> bool:
    """Check if a model field has any kind of index.

    Checks: db_index, unique, primary_key, ForeignKey (auto-indexed),
    and Meta.indexes / Meta.unique_together.
    """
    try:
        field = model._meta.get_field(field_name)
    except Exception:
        return True  # Unknown field — assume indexed to avoid false positives

    # Primary key is always indexed
    if getattr(field, "primary_key", False):
        return True

    # Explicit db_index
    if getattr(field, "db_index", False):
        return True

    # Unique fields get an index
    if getattr(field, "unique", False):
        return True

    # ForeignKey fields are auto-indexed by most backends
    from django.db.models import ForeignKey

    if isinstance(field, ForeignKey):
        return True

    # Check Meta.indexes
    for index in model._meta.indexes:
        index_fields = [f.removesuffix("_id") for f in index.fields]
        if field_name in index_fields:
            return True

    # Check Meta.unique_together
    return any(field_name in unique_set for unique_set in model._meta.unique_together)


def _extract_where_columns(normalized_sql: str) -> list[tuple[str, str]]:
    """Extract (table, column) pairs from WHERE clause."""
    # Find the WHERE clause
    where_match = re.search(
        r"\bWHERE\b(.+?)(?:\bORDER\b|\bGROUP\b|\bLIMIT\b|\bHAVING\b|$)",
        normalized_sql,
        re.IGNORECASE,
    )
    if not where_match:
        return []

    where_clause = where_match.group(1)
    return _WHERE_COL_RE.findall(where_clause)


def _extract_order_by_columns(normalized_sql: str) -> list[tuple[str, str]]:
    """Extract (table, column) pairs from ORDER BY clause."""
    order_match = _ORDER_BY_COL_RE.search(normalized_sql)
    if not order_match:
        return []

    order_clause = order_match.group(1)
    return _ORDER_COL_RE.findall(order_clause)


class MissingIndexAnalyzer(BaseAnalyzer):
    """Analyzer that detects queries on non-indexed columns.

    Examines WHERE and ORDER BY clauses to find columns that lack
    database indexes, and suggests adding db_index=True or Meta.indexes.
    """

    name: str = "missing_index"

    def analyze(
        self,
        queries: list[CapturedQuery],
        models_meta: dict[str, Any] | None = None,
    ) -> list[Prescription]:
        """Analyze queries for missing index issues.

        Args:
            queries: List of captured queries to analyze.
            models_meta: Optional model metadata (not used).

        Returns:
            List of prescriptions for detected missing index issues.
        """
        if not queries:
            return []

        try:
            return self._detect_missing_indexes(queries)
        except Exception:
            logger.warning("query_doctor: missing index analysis failed", exc_info=True)
            return []

    def _detect_missing_indexes(self, queries: list[CapturedQuery]) -> list[Prescription]:
        """Core missing index detection logic."""
        prescriptions: list[Prescription] = []
        seen: set[tuple[str, str]] = set()  # (table, column) pairs already reported

        for query in queries:
            if not query.is_select:
                continue

            normalized = query.normalized_sql

            # Extract columns from WHERE and ORDER BY
            where_cols = _extract_where_columns(normalized)
            order_cols = _extract_order_by_columns(normalized)

            all_cols = where_cols + order_cols

            for table, column in all_cols:
                if (table, column) in seen:
                    continue

                model = _get_model_for_table(table)
                if model is None:
                    continue

                if not _field_is_indexed(model, column):
                    seen.add((table, column))
                    prescriptions.append(self._build_prescription(table, column, model, query))

        return prescriptions

    def _build_prescription(
        self,
        table: str,
        column: str,
        model: Any,
        query: CapturedQuery,
    ) -> Prescription:
        """Build a missing index prescription."""
        model_name = model.__name__
        return Prescription(
            issue_type=IssueType.MISSING_INDEX,
            severity=Severity.INFO,
            description=(
                f'Missing index: column "{column}" on {model_name} (table "{table}") '
                f"is used in WHERE/ORDER BY but has no index"
            ),
            fix_suggestion=(
                f"Add db_index=True to {model_name}.{column}, or add to Meta.indexes: "
                f'indexes = [models.Index(fields=["{column}"], name="idx_{table}_{column}")]'
            ),
            callsite=query.callsite,
            query_count=1,
            fingerprint=query.fingerprint,
            extra={"table": table, "column": column, "model": model_name},
        )
