"""Write N+1 detection analyzer.

Detects repeated single-row write statements -- the ``.save()``, ``.create()``
or ``.delete()`` in a loop that issues one round trip per object where a single
bulk statement would do.

The other built-in analyzers all examine SELECTs. This one examines everything
else, which is why it carries its own statement parsing: ``extract_tables()``
reads FROM and JOIN clauses only, so an INSERT or UPDATE capture arrives with an
empty ``tables`` list and the table name has to come from the statement itself.

Algorithm:
1. Keep non-SELECT captures, dropping transaction control, DDL, and every bulk
   write form -- multi-row INSERTs, and UPDATE/DELETE statements whose IN list
   holds more than one value. None is a repeated single-row write.
2. Classify each as insert, update or delete, and read its target table.
3. Group by fingerprint -- normalization collapses literals, so the same
   statement shape repeated in a loop shares one fingerprint.
4. For each group at or over the threshold, prescribe the bulk equivalent.

Applying any of the three prescriptions clears the finding, which is why all
three bulk forms are rejected rather than only ``bulk_create()``'s. Counting
captures would not be enough: Django splits ``bulk_create()``, ``bulk_update()``
and a chunked queryset ``delete()`` into equal batches whenever ``batch_size=``
is passed or the backend caps parameters per statement, and those batches share
a fingerprint. Cardinality is read from the raw statement because normalization
collapses ``IN`` lists -- see ``_classify``.
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

# An IN list opening, as in WHERE "id" IN (%s, %s, %s).
_IN_LIST_RE = re.compile(r"\bin\s*\(", re.IGNORECASE)

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


def _string_mask(statement: str) -> list[bool]:
    """Mark every character that sits inside a single-quoted SQL literal.

    Both counters below walk characters looking for structural punctuation.
    Without this mask a comma or parenthesis inside a literal reads as a list
    separator or a row tuple, and the statement is misclassified as bulk --
    which suppresses the finding.

    A quote is escaped by doubling it (``''``), which is SQL's own rule, so
    the pair is consumed without ending the literal.

    Args:
        statement: The SQL to scan.

    Returns:
        One bool per character: True if that character is inside a literal
        (the surrounding quotes themselves count as inside).
    """
    mask = [False] * len(statement)
    inside = False
    index = 0
    length = len(statement)
    while index < length:
        char = statement[index]
        if char == "'":
            if inside and index + 1 < length and statement[index + 1] == "'":
                mask[index] = mask[index + 1] = True
                index += 2
                continue
            mask[index] = True
            inside = not inside
            index += 1
            continue
        mask[index] = inside
        index += 1
    return mask


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
    mask = _string_mask(statement)
    match = next(
        (m for m in _VALUES_RE.finditer(statement) if not mask[m.start()]),
        None,
    )
    if match is None:
        return 0

    depth = 0
    tuples = 0
    for index in range(match.end(), len(statement)):
        if mask[index]:
            continue
        char = statement[index]
        if char == "(":
            if depth == 0:
                tuples += 1
            depth += 1
        elif char == ")":
            if depth > 0:
                depth -= 1

    return tuples


def _max_in_list_size(statement: str) -> int:
    """Return the largest number of values held by any IN list in a statement.

    Used to tell a repeated single-row write from a repeated *bulk* one. One value
    in the IN list means the statement targets one row; more than one means it
    already targets many and is not this analyzer's finding.

    Counts comma-separated items at the list's own nesting depth rather than
    placeholder tokens, so it holds across paramstyles -- ``%s`` on most backends,
    ``:argN`` on Oracle -- and does not miscount a function call or a tuple
    nested inside a value.

    A list whose contents begin with SELECT is a subquery, not a value list, and
    counts 0: its cardinality is not visible in the statement. See the
    limitations noted on ``_classify``.
    """
    largest = 0
    mask = _string_mask(statement)

    for match in _IN_LIST_RE.finditer(statement):
        if mask[match.start()]:
            # The keyword itself is inside a literal, so there is no IN list.
            continue
        depth = 1
        items = 1
        body_start = match.end()
        end = body_start

        for index in range(body_start, len(statement)):
            if mask[index]:
                continue
            char = statement[index]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    end = index
                    break
            elif char == "," and depth == 1:
                items += 1

        if statement[body_start:end].lstrip().lower().startswith("select"):
            continue

        largest = max(largest, items)

    return largest


def _classify(normalized_sql: str, raw_sql: str) -> tuple[str, str] | None:
    """Classify a statement as (kind, table), or None if it is not a single-row write.

    Rejected: transaction control, DDL, multi-row INSERTs, and UPDATE/DELETE
    statements whose WHERE clause carries an IN list of more than one value. All
    three write kinds have a bulk form this analyzer prescribes, and every bulk
    form must be rejected -- otherwise the prescribed fix is reported as the
    defect, because Django splits each into equal batches that share a
    fingerprint.

    Both raw and normalized SQL are needed. Kind and table come from the
    normalized form; cardinality must come from the **raw** statement, because
    ``normalize_sql`` collapses ``IN (...)`` to ``IN (?)``
    (``fingerprint.py`` ``_RE_IN_CLAUSE``). A single-object ``obj.delete()`` and a
    batched ``filter(pk__in=[...]).delete()`` are normalized-identical, so a rule
    reading only the normalized form must either miss the false positive or
    silence the per-object delete loop that is this analyzer's whole point.

    Two residual false positives that statement shape cannot detect, documented
    in ``docs/analyzers/write-nplusone.md`` rather than guessed at:

    - ``WHERE id IN (SELECT ...)`` holds no value list, so it reads as single-row.
    - ``filter(status="x").delete()`` emits ``WHERE "status" = %s`` and can affect
      any number of rows with no IN list at all.
    """
    statement = normalized_sql.lstrip()

    if statement.startswith(_NON_WRITE_PREFIXES):
        return None

    for kind, pattern in _STATEMENT_PATTERNS:
        match = pattern.match(statement)
        if match:
            if kind == "insert":
                if _values_tuple_count(raw_sql) > 1:
                    return None
            elif _max_in_list_size(raw_sql) > 1:
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

            classification = _classify(query.normalized_sql, query.sql)
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
