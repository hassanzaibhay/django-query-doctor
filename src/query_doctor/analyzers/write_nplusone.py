"""Write N+1 detection analyzer.

Detects repeated single-row write statements -- the ``.save()``, ``.create()``
or ``.delete()`` in a loop that issues one round trip per object where a single
bulk statement would do.

The other built-in analyzers all examine SELECTs. This one examines everything
else, which is why it carries its own statement parsing: ``extract_tables()``
reads FROM and JOIN clauses only, so an INSERT or UPDATE capture arrives with an
empty ``tables`` list and the table name has to come from the statement itself.

Algorithm:
1. Keep non-SELECT captures, dropping transaction control, DDL and multi-row
   INSERTs -- none of which is a repeated single-row write.
2. Classify each as insert, update or delete, and read its target table.
3. Group by fingerprint -- normalization collapses literals, so the same
   statement shape repeated in a loop shares one fingerprint.
4. For each group at or over the threshold, prescribe the bulk equivalent.

Multi-row INSERTs -- what ``bulk_create()`` emits -- are rejected outright, so
applying the prescription clears the finding. Counting captures would not be
enough: Django splits ``bulk_create()`` into several equal multi-row INSERTs
whenever ``batch_size=`` is passed or the backend caps parameters per statement,
and those batches share a fingerprint.
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

# Transaction control and connection management. These are captured with
# is_select=False like any write -- a plain "BEGIN" arrives as an ordinary
# non-SELECT capture with its own fingerprint -- so without this filter a
# request opening several transactions would be reported as a write N+1.
_NON_WRITE_PREFIXES = (
    "begin",
    "commit",
    "rollback",
    "savepoint",
    "release",
    "set ",
    "pragma",
)

# INSERT INTO "table" (...) VALUES (...)
_INSERT_RE = re.compile(r'^insert\s+into\s+"?(\w+)"?', re.IGNORECASE)

# UPDATE "table" SET ...
_UPDATE_RE = re.compile(r'^update\s+"?(\w+)"?', re.IGNORECASE)

# DELETE FROM "table" WHERE ...
_DELETE_RE = re.compile(r'^delete\s+from\s+"?(\w+)"?', re.IGNORECASE)

# The VALUES keyword introducing an INSERT's row tuples.
_VALUES_RE = re.compile(r"\bvalues\b", re.IGNORECASE)

_STATEMENT_PATTERNS = (
    ("insert", _INSERT_RE),
    ("update", _UPDATE_RE),
    ("delete", _DELETE_RE),
)

# What to prescribe per statement kind. Keyed by the same token stored in
# Prescription.extra["statement"], so the report and the fix cannot drift.
_FIXES = {
    "insert": (
        "Build the objects in a list and issue one write: "
        "Model.objects.bulk_create([Model(...), ...]). "
        "Pass batch_size= if the list is large enough to strain the driver."
    ),
    "update": (
        "Collect the modified objects and issue one write: "
        "Model.objects.bulk_update(objects, ['field']). "
        "If every row gets the same value, a queryset update is cheaper still: "
        "Model.objects.filter(...).update(field=value)."
    ),
    "delete": (
        "Delete through the queryset instead of per object: "
        "Model.objects.filter(...).delete(), which issues one statement."
    ),
}


def _model_name_for_table(table_name: str) -> str | None:
    """Return the model class name backing a database table, if resolvable."""
    try:
        from django.apps import apps

        for model in apps.get_models():
            if model._meta.db_table == table_name:
                name: str = model.__name__
                return name
    except Exception:
        logger.debug("query_doctor: failed to resolve model for table", exc_info=True)
    return None


def _values_tuple_count(statement: str) -> int:
    """Count top-level tuples in an INSERT's VALUES clause.

    A depth-aware scan rather than a regex: a value can itself contain
    parentheses, and counting "(" would read one row with a subquery as many
    rows.

    Returns 0 for a statement with no row tuples, which covers both
    ``INSERT ... SELECT`` (no VALUES keyword) and ``INSERT ... DEFAULT VALUES``
    (the keyword is present but introduces nothing). Both are treated as
    single-row rather than bulk, so a loop issuing either is still reported.
    """
    match = _VALUES_RE.search(statement)
    if match is None:
        return 0

    depth = 0
    tuples = 0
    for char in statement[match.end() :]:
        if char == "(":
            if depth == 0:
                tuples += 1
            depth += 1
        elif char == ")":
            if depth > 0:
                depth -= 1

    return tuples


def _classify(normalized_sql: str) -> tuple[str, str] | None:
    """Classify a normalized statement as (kind, table).

    Returns None for anything that is not a repeated *single-row* write:
    transaction control, DDL, and multi-row INSERTs.
    """
    statement = normalized_sql.lstrip()

    if statement.startswith(_NON_WRITE_PREFIXES):
        return None

    for kind, pattern in _STATEMENT_PATTERNS:
        match = pattern.match(statement)
        if match:
            # A multi-row INSERT is the bulk form this analyzer prescribes, so it
            # must never be reported as the problem. Django splits bulk_create()
            # into several equal multi-row INSERTs whenever batch_size= is passed
            # or the backend caps parameters per statement (SQLite's 999-variable
            # limit, MySQL's packet size), and those batches share a fingerprint.
            # Without this check, bulk_create(objs, batch_size=3) over 9 objects
            # emits three INSERTs, clears the default threshold, and is reported
            # as three "single-row" writes -- the prescribed fix flagged as the
            # defect.
            if kind == "insert" and _values_tuple_count(statement) > 1:
                return None
            return kind, match.group(1)

    return None


class WriteNPlusOneAnalyzer(BaseAnalyzer):
    """Analyzer that detects repeated single-row writes.

    Groups non-SELECT queries by fingerprint and reports groups at or over the
    configured threshold, prescribing the bulk statement that replaces them.
    """

    name: str = "write_nplusone"

    def analyze(
        self,
        queries: list[CapturedQuery],
        models_meta: dict[str, Any] | None = None,
    ) -> list[Prescription]:
        """Analyze queries for repeated single-row writes.

        Args:
            queries: List of captured queries to analyze.
            models_meta: Optional model metadata (not used currently).

        Returns:
            List of prescriptions for detected write N+1 issues.
        """
        if not queries or not self.is_enabled():
            return []

        try:
            return self._detect_write_nplusone(queries)
        except Exception:
            logger.warning("query_doctor: write N+1 analysis failed", exc_info=True)
            return []

    def _detect_write_nplusone(self, queries: list[CapturedQuery]) -> list[Prescription]:
        """Core write N+1 detection logic."""
        config = get_config()
        threshold = config["ANALYZERS"]["write_nplusone"].get("threshold", 3)

        groups: dict[str, list[CapturedQuery]] = defaultdict(list)
        classifications: dict[str, tuple[str, str]] = {}

        for query in queries:
            if query.is_select:
                continue

            classification = _classify(query.normalized_sql)
            if classification is None:
                continue

            groups[query.fingerprint].append(query)
            classifications[query.fingerprint] = classification

        prescriptions: list[Prescription] = []

        for fingerprint, group in groups.items():
            if len(group) < threshold:
                continue

            kind, table = classifications[fingerprint]
            prescriptions.append(self._build_prescription(group, kind, table, fingerprint))

        return prescriptions

    def _build_prescription(
        self,
        group: list[CapturedQuery],
        kind: str,
        table: str,
        fingerprint: str,
    ) -> Prescription:
        """Build a write N+1 prescription."""
        count = len(group)
        total_time = sum(q.duration_ms for q in group)
        severity = Severity.CRITICAL if count >= 10 else Severity.WARNING
        callsite = next((q.callsite for q in group if q.callsite), None)

        model_name = _model_name_for_table(table)
        subject = model_name or f'table "{table}"'
        fix = _FIXES[kind]
        if model_name:
            fix = fix.replace("Model.objects", f"{model_name}.objects").replace(
                "Model(...)", f"{model_name}(...)"
            )

        return Prescription(
            issue_type=IssueType.WRITE_N_PLUS_ONE,
            severity=severity,
            description=(
                f"Write N+1 detected: {count} single-row {kind.upper()} statements "
                f"for {subject}. One bulk statement replaces all {count}."
            ),
            fix_suggestion=fix,
            callsite=callsite,
            query_count=count,
            # A bulk statement is one round trip instead of count, so the saving
            # is everything but the first. Same shape as NPlusOneAnalyzer.
            time_saved_ms=total_time * (count - 1) / count if count > 0 else 0,
            fingerprint=fingerprint,
            extra={"table": table, "statement": kind, "model": model_name},
        )
