"""Fat SELECT analyzer for detecting overly broad column selection.

Detects SELECT queries that fetch many columns when only a few are needed.
Suggests using .only() or .defer() to reduce data transfer.

Algorithm:
1. Parse each SELECT query to extract selected columns
2. If column count >= threshold, flag as fat SELECT
3. Suggest .defer() for large fields (TextField, etc.) or .only() for narrow usage
"""

from __future__ import annotations

import logging
import re
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

# Matches column references like "table"."column"
_COLUMN_RE = re.compile(r'"(\w+)"\."\w+"', re.IGNORECASE)

# Extracts columns between SELECT and FROM
_SELECT_COLS_RE = re.compile(
    r"SELECT\s+(.*?)\s+FROM\s+",
    re.IGNORECASE | re.DOTALL,
)

# Extract table name from FROM clause
_FROM_TABLE_RE = re.compile(
    r'FROM\s+"?(\w+)"?',
    re.IGNORECASE,
)

# A lookup that can return at most one row: a primary-key equality test, or
# an explicit LIMIT 1. Neither is a data-transfer problem however wide the
# row is, and the pk form is the most ordinary operation in Django.
_PK_EQUALITY_RE = re.compile(r'WHERE\s+"?\w+"?\."?id"?\s*=\s*\?', re.IGNORECASE)
_LIMIT_ONE_RE = re.compile(r"\bLIMIT\s+1\b", re.IGNORECASE)

# Default threshold -- flag SELECTs with this many columns or more
_DEFAULT_FIELD_COUNT_THRESHOLD = 8


class FatSelectAnalyzer(BaseAnalyzer):
    """Analyzer that detects overly broad SELECT queries.

    Flags queries that select many columns and suggests using
    .only() or .defer() to reduce data transfer.
    """

    name: str = "fat_select"

    def __init__(self, field_count_threshold: int | None = None) -> None:
        """Initialize the analyzer.

        Args:
            field_count_threshold: Minimum number of columns to flag.
                                  Defaults to config or 8.
        """
        self._threshold_override = field_count_threshold

    def analyze(
        self,
        queries: list[CapturedQuery],
        models_meta: dict[str, Any] | None = None,
    ) -> list[Prescription]:
        """Analyze queries for fat SELECT patterns.

        Args:
            queries: List of captured queries to analyze.
            models_meta: Optional model metadata (not used currently).

        Returns:
            List of prescriptions for detected fat SELECT issues.
        """
        if not queries or not self.is_enabled():
            return []

        try:
            return self._detect_fat_selects(queries)
        except Exception:
            logger.warning("query_doctor: fat SELECT analysis failed", exc_info=True)
            return []

    def _get_threshold(self) -> int:
        """Get the field count threshold from config or override."""
        if self._threshold_override is not None:
            return self._threshold_override
        try:
            config = get_config()
            return int(
                config.get("ANALYZERS", {})
                .get("fat_select", {})
                .get("threshold", _DEFAULT_FIELD_COUNT_THRESHOLD)
            )
        except Exception:
            return _DEFAULT_FIELD_COUNT_THRESHOLD

    def _detect_fat_selects(self, queries: list[CapturedQuery]) -> list[Prescription]:
        """Core fat SELECT detection logic."""
        threshold = self._get_threshold()
        prescriptions: list[Prescription] = []
        seen_tables: set[str] = set()

        for query in queries:
            if not query.is_select:
                continue

            sql = query.normalized_sql or query.sql
            if self._is_single_row_lookup(sql):
                continue

            table = self._extract_table(sql)
            if not table or table in seen_tables:
                continue

            # Count only the columns belonging to the table the message will
            # name. Counting the whole select list attributes a joined
            # table's columns to the base table, so the number does not mean
            # what it says and .defer() cannot shrink it proportionally.
            columns = self._extract_columns(sql, table)
            if not columns or len(columns) < threshold:
                continue

            seen_tables.add(table)

            large_fields = self._find_large_fields(table, columns)
            prescription = self._build_prescription(query, table, columns, large_fields)
            prescriptions.append(prescription)

        return prescriptions

    @staticmethod
    def _is_single_row_lookup(sql: str) -> bool:
        """Report whether the statement can return at most one row.

        Args:
            sql: The normalized SQL of the query.

        Returns:
            True for a primary-key equality test or an explicit LIMIT 1.
        """
        return bool(_PK_EQUALITY_RE.search(sql) or _LIMIT_ONE_RE.search(sql))

    def _extract_columns(self, sql: str, table: str | None = None) -> list[str]:
        """Extract the selected column names, optionally for one table only.

        Args:
            sql: The SQL to read the select list from.
            table: When given, keep only columns qualified by this table.

        Returns:
            The column names, in select-list order.
        """
        match = _SELECT_COLS_RE.search(sql)
        if not match:
            return []

        cols_str = match.group(1)
        if cols_str.strip() == "*":
            return ["*"]

        col_matches = re.findall(r'"(\w+)"\."(\w+)"', cols_str)
        return [col for qualifier, col in col_matches if table is None or qualifier == table]

    def _extract_table(self, sql: str) -> str | None:
        """Extract the main table name from a SQL query."""
        match = _FROM_TABLE_RE.search(sql)
        return match.group(1) if match else None

    def _find_large_fields(self, table: str, columns: list[str]) -> list[str]:
        """Identify large fields (TextField, etc.) in the selected columns."""
        large_fields: list[str] = []
        try:
            model = self._get_model_for_table(table)
            if model is None:
                return large_fields

            from django.db import models as django_models

            large_types = (
                django_models.TextField,
                django_models.BinaryField,
            )

            for col_name in columns:
                try:
                    field = model._meta.get_field(col_name)
                    if isinstance(field, large_types):
                        large_fields.append(col_name)
                except Exception:
                    continue
        except Exception:
            pass
        return large_fields

    def _get_model_for_table(self, table_name: str) -> Any | None:
        """Look up a Django model class by its database table name."""
        try:
            from django.apps import apps

            for model in apps.get_models():
                if model._meta.db_table == table_name:
                    return model
        except Exception:
            pass
        return None

    def _build_prescription(
        self,
        query: CapturedQuery,
        table: str,
        columns: list[str],
        large_fields: list[str],
    ) -> Prescription:
        """Build a fat SELECT prescription."""
        col_count = len(columns)

        if large_fields:
            fields_str = ", ".join(f"'{f}'" for f in large_fields)
            fix = (
                f"Use .defer({fields_str}) to skip loading large fields, "
                "or .values()/.values_list() if you don't need model instances"
            )
            desc = (
                f"Fat SELECT: {col_count} columns from "
                f'"{table}" including large fields: {", ".join(large_fields)}'
            )
        else:
            fix = (
                "Use .only('field1', 'field2', ...) to select "
                "only the fields you need, .defer() to skip large fields, "
                "or .values()/.values_list() if you don't need model instances"
            )
            desc = f'Fat SELECT: {col_count} columns from "{table}"'

        return Prescription(
            issue_type=IssueType.FAT_SELECT,
            severity=Severity.INFO,
            description=desc,
            fix_suggestion=fix,
            callsite=query.callsite,
            query_count=1,
            time_saved_ms=0,
            fingerprint=query.fingerprint,
            extra={"table": table, "column_count": col_count, "large_fields": large_fields},
        )
