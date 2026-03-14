"""Query complexity analyzer for django-query-doctor.

Scores SQL query complexity using regex-based pattern matching and flags
overly complex queries that may benefit from decomposition or optimization.
"""

from __future__ import annotations

import re
from typing import Any

from query_doctor.analyzers.base import BaseAnalyzer
from query_doctor.conf import get_config
from query_doctor.types import CapturedQuery, IssueType, Prescription, Severity

# Pre-compiled regex patterns for complexity scoring
_RE_JOIN = re.compile(r"\bJOIN\b")
_RE_SELECT = re.compile(r"\bSELECT\b")
_RE_OR = re.compile(r"\bOR\b")
_RE_GROUP_BY = re.compile(r"\bGROUP\s+BY\b")
_RE_HAVING = re.compile(r"\bHAVING\b")
_RE_DISTINCT = re.compile(r"\bDISTINCT\b")
_RE_ORDER_BY = re.compile(r"\bORDER\s+BY\b")
_RE_WHEN = re.compile(r"\bWHEN\b")
_RE_SET_OPS = re.compile(r"\b(UNION|INTERSECT|EXCEPT)\b")
_RE_LIKE_LEADING = re.compile(r"LIKE\s+'%", re.IGNORECASE)
_RE_COUNT = re.compile(r"\bCOUNT\s*\(")


class QueryComplexityAnalyzer(BaseAnalyzer):
    """Analyzes SQL queries for excessive complexity.

    Scores queries based on structural patterns (JOINs, subqueries,
    aggregations, etc.) and flags those exceeding a configurable threshold.
    """

    name = "complexity"

    def analyze(
        self,
        queries: list[CapturedQuery],
        models_meta: dict[str, Any] | None = None,
    ) -> list[Prescription]:
        """Analyze captured queries for excessive complexity.

        Args:
            queries: List of captured SQL queries to analyze.
            models_meta: Optional Django model metadata (unused).

        Returns:
            List of Prescription objects for overly complex queries.
        """
        if not self.is_enabled():
            return []

        config = get_config()
        analyzer_conf = config.get("ANALYZERS", {}).get("complexity", {})
        threshold = analyzer_conf.get("threshold", 8)

        prescriptions: list[Prescription] = []

        for q in queries:
            if not q.is_select:
                continue

            score = self._score_complexity(q.normalized_sql)
            if score >= threshold:
                severity = Severity.CRITICAL if score >= 12 else Severity.WARNING
                prescriptions.append(
                    Prescription(
                        issue_type=IssueType.QUERY_COMPLEXITY,
                        severity=severity,
                        description=(
                            f"Query complexity score {score} exceeds threshold {threshold}"
                        ),
                        fix_suggestion=self._suggest_simplification(q.normalized_sql, score),
                        callsite=q.callsite,
                    )
                )

        return prescriptions

    def _score_complexity(self, sql: str) -> int:
        """Score the complexity of a normalized SQL query.

        Args:
            sql: The normalized (lowercased) SQL string.

        Returns:
            Integer complexity score.
        """
        score = 0
        upper = sql.upper()

        # Each JOIN: +2
        join_count = len(_RE_JOIN.findall(upper))
        score += join_count * 2

        # Each subquery (SELECT inside SELECT): +3
        select_count = len(_RE_SELECT.findall(upper))
        if select_count > 1:
            score += (select_count - 1) * 3

        # Each OR in WHERE: +1
        score += len(_RE_OR.findall(upper))

        # GROUP BY: +2
        if _RE_GROUP_BY.search(upper):
            score += 2

        # HAVING: +2
        if _RE_HAVING.search(upper):
            score += 2

        # DISTINCT: +1
        if _RE_DISTINCT.search(upper):
            score += 1

        # ORDER BY: +1
        if _RE_ORDER_BY.search(upper):
            score += 1

        # CASE/WHEN: +1 each
        score += len(_RE_WHEN.findall(upper))

        # UNION/INTERSECT/EXCEPT: +3
        if _RE_SET_OPS.search(upper):
            score += 3

        # LIKE with leading %: +2
        if _RE_LIKE_LEADING.search(upper) or _RE_LIKE_LEADING.search(sql):
            score += 2

        # COUNT(*) with JOIN: +2
        if _RE_COUNT.search(upper) and _RE_JOIN.search(upper):
            score += 2

        return score

    def _suggest_simplification(self, sql: str, score: int) -> str:
        """Generate contextual simplification suggestions.

        Args:
            sql: The normalized SQL string.
            score: The computed complexity score.

        Returns:
            Human-readable suggestion string.
        """
        suggestions: list[str] = []
        upper = sql.upper()

        join_count = len(_RE_JOIN.findall(upper))
        if join_count > 3:
            suggestions.append(
                f"Consider breaking this query into smaller queries — "
                f"{join_count} JOINs detected. Use select_related for 1-2 "
                f"FKs and prefetch_related for the rest."
            )

        select_count = len(_RE_SELECT.findall(upper))
        if select_count > 1:
            suggestions.append("Replace subqueries with JOINs or annotate() where possible.")

        or_count = len(_RE_OR.findall(upper))
        if or_count > 2:
            suggestions.append(
                "Multiple OR conditions prevent index usage. Consider using "
                "Q objects with separate filtered querysets combined via union()."
            )

        if not suggestions:
            suggestions.append(
                "Consider breaking into multiple simpler queries or using database views."
            )

        return " ".join(suggestions)
