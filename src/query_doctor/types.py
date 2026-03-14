"""Core data structures for django-query-doctor.

Defines the contract types used across all modules: query captures,
prescriptions, diagnosis reports, and supporting enums.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(Enum):
    """Severity level for a diagnosed issue."""

    CRITICAL = "critical"  # N+1 with 10+ queries
    WARNING = "warning"  # N+1 with 3-9, duplicates
    INFO = "info"  # Suggestions (only, defer)


class IssueType(Enum):
    """Type of query optimization issue."""

    N_PLUS_ONE = "n_plus_one"
    DUPLICATE_QUERY = "duplicate_query"
    MISSING_INDEX = "missing_index"
    FAT_SELECT = "fat_select"
    QUERYSET_EVAL = "queryset_eval"
    DRF_SERIALIZER = "drf_serializer"
    QUERY_COMPLEXITY = "complexity"


@dataclass(frozen=True)
class CallSite:
    """Where in user code a query originated."""

    filepath: str
    line_number: int
    function_name: str
    code_context: str = ""  # The actual line of code if available


@dataclass(frozen=True)
class CapturedQuery:
    """A single SQL query captured during a request."""

    sql: str
    params: tuple[Any, ...] | None
    duration_ms: float
    fingerprint: str  # Normalized SQL hash
    normalized_sql: str  # SQL with params replaced by ?
    callsite: CallSite | None
    is_select: bool
    tables: list[str]  # Tables referenced in the query


@dataclass
class Prescription:
    """A diagnosed issue with an actionable fix."""

    issue_type: IssueType
    severity: Severity
    description: str  # Human-readable: "N+1 detected: 47 queries for Author"
    fix_suggestion: str  # Exact code: "Add .select_related('author') to queryset"
    callsite: CallSite | None
    query_count: int = 0  # How many queries this issue involves
    time_saved_ms: float = 0  # Estimated time saved if fixed
    fingerprint: str = ""  # Which query pattern this relates to
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiagnosisReport:
    """Complete report for one request/context."""

    prescriptions: list[Prescription] = field(default_factory=list)
    total_queries: int = 0
    total_time_ms: float = 0
    captured_queries: list[CapturedQuery] = field(default_factory=list)

    @property
    def issues(self) -> int:
        """Return the total number of diagnosed issues."""
        return len(self.prescriptions)

    @property
    def n_plus_one_count(self) -> int:
        """Return the count of N+1 query issues."""
        return sum(1 for p in self.prescriptions if p.issue_type == IssueType.N_PLUS_ONE)

    @property
    def has_critical(self) -> bool:
        """Return True if any prescription has CRITICAL severity."""
        return any(p.severity == Severity.CRITICAL for p in self.prescriptions)
