"""QuerySet evaluation pattern analyzer.

Detects inefficient queryset evaluation patterns by inspecting call site
code context. Identifies cases where Django provides more efficient methods:

- len(qs) → qs.count() (avoids loading all rows into memory)
- bool(qs) / if qs → qs.exists() (stops at first row)
- list(qs)[0] → qs.first() (avoids loading entire queryset)

Algorithm:
1. For each SELECT query with a callsite and code_context
2. Check code_context against known inefficient patterns
3. Generate Prescription with the efficient alternative
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

# Pattern: len(SomeQueryset...)
_LEN_PATTERN = re.compile(r"\blen\s*\(", re.IGNORECASE)

# Pattern: bool(SomeQueryset...) or if SomeQueryset:
_BOOL_PATTERN = re.compile(r"(?:\bbool\s*\(|^\s*if\s+\w)", re.IGNORECASE)

# Pattern: list(...)[0] or list(...)[index]
_LIST_INDEX_PATTERN = re.compile(r"\blist\s*\(.*\)\s*\[\s*\d+\s*\]", re.IGNORECASE)


class QuerySetEvalAnalyzer(BaseAnalyzer):
    """Analyzer that detects inefficient queryset evaluation patterns.

    Inspects call site code context to find patterns where Django provides
    more efficient alternatives (count, exists, first).
    """

    name: str = "queryset_eval"

    def analyze(
        self,
        queries: list[CapturedQuery],
        models_meta: dict[str, Any] | None = None,
    ) -> list[Prescription]:
        """Analyze queries for inefficient evaluation patterns.

        Args:
            queries: List of captured queries to analyze.
            models_meta: Optional model metadata (not used).

        Returns:
            List of prescriptions for detected evaluation issues.
        """
        if not queries or not self.is_enabled():
            return []

        try:
            return self._detect_eval_patterns(queries)
        except Exception:
            logger.warning("query_doctor: queryset eval analysis failed", exc_info=True)
            return []

    def _detect_eval_patterns(self, queries: list[CapturedQuery]) -> list[Prescription]:
        """Core evaluation pattern detection logic."""
        prescriptions: list[Prescription] = []

        for query in queries:
            if not query.is_select:
                continue
            if not query.callsite or not query.callsite.code_context:
                continue

            code = query.callsite.code_context

            # Check patterns in order of severity/specificity
            if _LIST_INDEX_PATTERN.search(code):
                prescriptions.append(
                    self._build_prescription(
                        query=query,
                        pattern="list(qs)[0]",
                        suggestion=(
                            "Use .first() instead of list(qs)[0] "
                            "to avoid loading the entire queryset"
                        ),
                    )
                )
            elif _LEN_PATTERN.search(code):
                prescriptions.append(
                    self._build_prescription(
                        query=query,
                        pattern="len(qs)",
                        suggestion="Use .count() instead of len() to let the database count rows",
                    )
                )
            elif _BOOL_PATTERN.search(code):
                prescriptions.append(
                    self._build_prescription(
                        query=query,
                        pattern="bool(qs)",
                        suggestion=(
                            "Use .exists() instead of bool()/if "
                            "to check for rows without loading them"
                        ),
                    )
                )

        return prescriptions

    def _build_prescription(
        self,
        query: CapturedQuery,
        pattern: str,
        suggestion: str,
    ) -> Prescription:
        """Build a queryset evaluation prescription."""
        return Prescription(
            issue_type=IssueType.QUERYSET_EVAL,
            severity=Severity.INFO,
            description=f"Inefficient queryset evaluation: {pattern}",
            fix_suggestion=suggestion,
            callsite=query.callsite,
            query_count=1,
            time_saved_ms=0,
            fingerprint=query.fingerprint,
            extra={"pattern": pattern},
        )
