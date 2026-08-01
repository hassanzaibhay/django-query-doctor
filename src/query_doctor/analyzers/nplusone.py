"""N+1 query detection analyzer.

Detects N+1 query patterns by grouping captured queries by fingerprint
and checking for repeated SELECT queries that indicate missing
select_related() or prefetch_related() calls.

Algorithm:
1. Group queries by fingerprint
2. For each group with count >= threshold:
   a. Check if it's a SELECT query with a WHERE clause
   b. Determine if it's a PK lookup (FK) or a through-table lookup (M2M)
   c. Resolve a relation name against a real model's _meta
3. Generate Prescription with exact fix suggestion

Invariant: a prescription never names a field that has not been resolved
through ``Model._meta.get_field()``. Where no relation was traversed -- a
``get(pk=...)`` loop, say -- there is nothing to name, and the prescription
is a bulk fetch rather than a guessed relation. A guessed name raises
``FieldError`` the moment a user follows it.
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

# Matches WHERE "table"."id" = ? (PK lookup -- FK N+1 access)
_PK_LOOKUP_RE = re.compile(
    r'where\s+"?(\w+)"?\."?id"?\s*=\s*\?',
    re.IGNORECASE,
)

# Matches WHERE "table"."something_id" = ? (FK column lookup -- M2M or reverse FK)
_FK_COL_LOOKUP_RE = re.compile(
    r'where\s+"?(\w+)"?\."?(\w+_id)"?\s*=\s*\?',
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


def _model_label(model: Any) -> str:
    """Return the ``app_label.ModelName`` label Django's app registry accepts."""
    return f"{model._meta.app_label}.{model.__name__}"


def _resolves_on(model: Any, field_name: str) -> bool:
    """Report whether ``field_name`` is a real field or relation on ``model``.

    This is the single check that stands between an analyzer guess and a
    prescription. A name that does not pass it is never put in front of a
    user, because following it raises ``FieldError``.
    """
    try:
        model._meta.get_field(field_name)
    except Exception:
        return False
    return True


def _find_forward_fk(target_table: str, source_tables: set[str]) -> tuple[Any, str] | None:
    """Find an FK that reaches ``target_table`` from a table already queried.

    Restricting the search to tables the capture actually read is what makes
    the answer usable: a global scan finds FK fields on models the caller
    never touched, and naming one of those produces advice that cannot be
    applied to the caller's queryset.

    Args:
        target_table: The db table being fetched one row at a time.
        source_tables: Tables read by queries that ran before the repeated group.

    Returns:
        ``(model, field_name)`` for a validated forward FK, or None.
    """
    try:
        target_model = _get_model_for_table(target_table)
        if target_model is None:
            return None

        from django.apps import apps

        for model in apps.get_models():
            if model._meta.db_table not in source_tables:
                continue
            if model._meta.db_table == target_table:
                continue
            for field in model._meta.get_fields():
                if (
                    getattr(field, "related_model", None) is target_model
                    and getattr(field, "many_to_one", False)
                    and hasattr(field, "name")
                    and _resolves_on(model, field.name)
                ):
                    return model, field.name
    except Exception:
        logger.debug("query_doctor: forward FK resolution failed", exc_info=True)
    return None


def _find_reverse_accessor(where_table: str, fk_column: str) -> tuple[Any, str] | None:
    """Resolve ``where_table.fk_column`` to the reverse accessor on the far side.

    A query shaped ``WHERE "book"."author_id" = ?`` is issued while iterating
    *authors*, so the name to prefetch is Author's reverse accessor for that
    FK (``books``) -- not ``author``, which is Book's field and does not
    resolve on Author.

    Returns:
        ``(owner_model, accessor_name)`` where ``accessor_name`` is validated
        against ``owner_model``, or None if it cannot be resolved.
    """
    try:
        child_model = _get_model_for_table(where_table)
        if child_model is None:
            return None
        for field in child_model._meta.get_fields():
            if getattr(field, "column", None) != fk_column:
                continue
            owner_model = getattr(field, "related_model", None)
            remote = getattr(field, "remote_field", None)
            if owner_model is None or remote is None:
                continue
            accessor = remote.get_accessor_name()
            if accessor and _resolves_on(owner_model, accessor):
                return owner_model, accessor
    except Exception:
        logger.debug("query_doctor: reverse accessor resolution failed", exc_info=True)
    return None


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
        if not queries or not self.is_enabled():
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

            prescription = self._classify_and_prescribe(
                group, normalized, fp, self._tables_read_before(queries, sample)
            )
            if prescription:
                prescriptions.append(prescription)

        return prescriptions

    @staticmethod
    def _tables_read_before(queries: list[CapturedQuery], first: CapturedQuery) -> set[str]:
        """Collect the tables read by queries that ran before ``first``.

        A forward-FK N+1 is always preceded by the query that loaded the rows
        being iterated, so this set is what makes it distinguishable from a
        bare ``get(pk=...)`` loop, which has no such predecessor.
        """
        tables: set[str] = set()
        for q in queries:
            if q is first:
                break
            tables.update(q.tables)
        return tables

    def _classify_and_prescribe(
        self,
        group: list[CapturedQuery],
        normalized: str,
        fp: str,
        source_tables: set[str],
    ) -> Prescription | None:
        """Classify the N+1 pattern and build a prescription."""
        # First check: WHERE "table"."something_id" = ?
        # This could be a M2M through-table access or reverse FK
        fk_col_match = _FK_COL_LOOKUP_RE.search(normalized)
        if fk_col_match:
            where_table = fk_col_match.group(1)
            fk_column = fk_col_match.group(2)

            # Check if the WHERE table is a through table -> M2M.
            # The field lives on the through table's parent model, which
            # _is_through_table() reports, so it is already model-scoped.
            through_info = _is_through_table(where_table)
            if through_info:
                parent = through_info["parent_model"]
                field_name = through_info["field_name"]
                if _resolves_on(parent, field_name):
                    return self._build_relation_prescription(
                        group=group,
                        table=where_table,
                        model=parent,
                        field_name=field_name,
                        strategy="prefetch_related",
                        fp=fp,
                    )

            # A regular FK-column lookup: the caller is iterating the far side
            # of the FK, so the name to prefetch is the reverse accessor, not
            # the column stem. Reading the stem off "author_id" yields Book's
            # field name and raises on an Author queryset (entry 49's class).
            reverse = _find_reverse_accessor(where_table, fk_column)
            if reverse is not None:
                owner_model, accessor = reverse
                return self._build_relation_prescription(
                    group=group,
                    table=where_table,
                    model=owner_model,
                    field_name=accessor,
                    strategy="prefetch_related",
                    fp=fp,
                )
            return self._build_bulk_fetch_prescription(
                group=group,
                table=where_table,
                model=_get_model_for_table(where_table),
                fp=fp,
            )

        # Second check: WHERE "table"."id" = ? (PK lookup)
        pk_match = _PK_LOOKUP_RE.search(normalized)
        if pk_match:
            target_table = pk_match.group(1)
            forward = _find_forward_fk(target_table, source_tables)
            if forward is not None:
                source_model, field_name = forward
                return self._build_relation_prescription(
                    group=group,
                    table=target_table,
                    model=source_model,
                    field_name=field_name,
                    strategy="select_related",
                    fp=fp,
                )
            # Nothing was traversed to get here -- this is a get(pk=...) loop.
            # select_related cannot help and there is no field to name, so
            # prescribe the fix that is always both valid and an improvement.
            return self._build_bulk_fetch_prescription(
                group=group,
                table=target_table,
                model=_get_model_for_table(target_table),
                fp=fp,
            )

        return None

    def _build_relation_prescription(
        self,
        group: list[CapturedQuery],
        table: str,
        model: Any,
        field_name: str,
        strategy: str,
        fp: str,
    ) -> Prescription:
        """Build a prescription naming a relation validated against ``model``.

        Args:
            group: The repeated queries forming the N+1.
            table: The db table the repeated queries read.
            model: The model the prescribed call must be made on.
            field_name: A relation name that resolves on ``model``.
            strategy: Either ``select_related`` or ``prefetch_related``.
            fp: The shared fingerprint of the group.

        Returns:
            The prescription to report.
        """
        label = _model_label(model)
        suggestion = f"Add .{strategy}('{field_name}') to your {model.__name__} queryset"
        if strategy == "prefetch_related":
            suggestion += f". For advanced filtering, use Prefetch('{field_name}', queryset=...)"
        return self._finish(
            group=group,
            fp=fp,
            description=(
                f'N+1 detected: {len(group)} queries for table "{table}" '
                f"(via {model.__name__}.{field_name})"
            ),
            suggestion=suggestion,
            extra={
                "table": table,
                "field": field_name,
                "model": label,
                "strategy": strategy,
            },
        )

    def _build_bulk_fetch_prescription(
        self,
        group: list[CapturedQuery],
        table: str,
        model: Any | None,
        fp: str,
    ) -> Prescription:
        """Build the relation-free prescription for a per-row primary-key loop.

        Names no field, because no relation was traversed and any field named
        here would be a guess. The wording deliberately contains neither
        ``select_related(`` nor ``prefetch_related(``: the auto-fixer keys off
        those tokens, and a token here would make it write a call that cannot
        apply to the caller's queryset.

        Args:
            group: The repeated queries forming the N+1.
            table: The db table the repeated queries read.
            model: The model for ``table``, or None if it maps to no model.
            fp: The shared fingerprint of the group.

        Returns:
            The prescription to report.
        """
        name = model.__name__ if model is not None else table
        return self._finish(
            group=group,
            fp=fp,
            description=(
                f'N+1 detected: {len(group)} queries for table "{table}" '
                f"(one row per iteration, no relation traversed)"
            ),
            suggestion=(
                f"Fetch the rows in one query: {name}.objects.in_bulk(ids), or "
                f"{name}.objects.filter(pk__in=ids), instead of one lookup per iteration"
            ),
            extra={
                "table": table,
                "field": None,
                "model": _model_label(model) if model is not None else None,
                "strategy": "bulk_fetch",
            },
        )

    def _finish(
        self,
        group: list[CapturedQuery],
        fp: str,
        description: str,
        suggestion: str,
        extra: dict[str, Any],
    ) -> Prescription:
        """Assemble the severity, timing and callsite shared by every branch."""
        count = len(group)
        total_time = sum(q.duration_ms for q in group)
        return Prescription(
            issue_type=IssueType.N_PLUS_ONE,
            severity=Severity.CRITICAL if count >= 10 else Severity.WARNING,
            description=description,
            fix_suggestion=suggestion,
            callsite=next((q.callsite for q in group if q.callsite), None),
            query_count=count,
            time_saved_ms=total_time * (count - 1) / count if count > 0 else 0,
            fingerprint=fp,
            extra=extra,
        )
