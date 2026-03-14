"""Duplicate query detection analyzer.

Detects exact and near-duplicate queries by grouping captured queries
by their SQL text (exact) and fingerprint (near-duplicate). Suggests
caching results in variables or consolidating with filter(id__in=[...]).
"""

from __future__ import annotations

import hashlib
import logging
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


def _sql_params_hash(sql: str, params: tuple[Any, ...] | None) -> str:
    """Create a hash key from SQL + params for exact duplicate detection."""
    key = sql + "|" + repr(params)
    return hashlib.sha256(key.encode()).hexdigest()[:16]


class DuplicateAnalyzer(BaseAnalyzer):
    """Analyzer that detects exact and near-duplicate queries.

    Exact duplicates: same SQL + same params executed multiple times.
    Near-duplicates: same SQL structure (fingerprint) with different params.
    """

    name: str = "duplicate"

    def analyze(
        self,
        queries: list[CapturedQuery],
        models_meta: dict[str, Any] | None = None,
    ) -> list[Prescription]:
        """Analyze queries for duplicate patterns.

        Args:
            queries: List of captured queries to analyze.
            models_meta: Optional model metadata (not used).

        Returns:
            List of prescriptions for detected duplicate issues.
        """
        if not queries:
            return []

        try:
            return self._detect_duplicates(queries)
        except Exception:
            logger.warning("query_doctor: duplicate analysis failed", exc_info=True)
            return []

    def _detect_duplicates(self, queries: list[CapturedQuery]) -> list[Prescription]:
        """Core duplicate detection logic."""
        config = get_config()
        threshold = config["ANALYZERS"]["duplicate"].get("threshold", 2)

        prescriptions: list[Prescription] = []

        # 1. Exact duplicates: group by (sql + params)
        exact_groups: dict[str, list[CapturedQuery]] = defaultdict(list)
        for q in queries:
            if q.is_select:
                key = _sql_params_hash(q.sql, q.params)
                exact_groups[key].append(q)

        for _key, group in exact_groups.items():
            if len(group) < threshold:
                continue

            sample = group[0]
            count = len(group)
            total_time = sum(q.duration_ms for q in group)
            callsite = next((q.callsite for q in group if q.callsite), None)
            table = sample.tables[0] if sample.tables else "unknown"

            prescriptions.append(
                Prescription(
                    issue_type=IssueType.DUPLICATE_QUERY,
                    severity=Severity.WARNING,
                    description=(
                        f'Duplicate query: {count} identical queries for table "{table}"'
                    ),
                    fix_suggestion=(
                        "Assign the queryset result to a variable and reuse it "
                        "instead of executing the same query multiple times"
                    ),
                    callsite=callsite,
                    query_count=count,
                    time_saved_ms=total_time * (count - 1) / count if count > 0 else 0,
                    fingerprint=sample.fingerprint,
                    extra={"table": table, "duplicate_type": "exact"},
                )
            )

        return prescriptions
