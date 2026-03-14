"""Exception hierarchy for django-query-doctor.

All package exceptions inherit from QueryDoctorError to allow
callers to catch any query-doctor-specific error with a single except clause.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from query_doctor.types import DiagnosisReport


class QueryDoctorError(Exception):
    """Base exception for all django-query-doctor errors."""


class ConfigError(QueryDoctorError):
    """Raised when there is a configuration error."""


class AnalyzerError(QueryDoctorError):
    """Raised when an analyzer encounters an error."""


class InterceptorError(QueryDoctorError):
    """Raised when the query interceptor encounters an error."""


class QueryBudgetError(QueryDoctorError):
    """Raised when a function exceeds its query budget.

    Attributes:
        report: The DiagnosisReport from the function execution.
    """

    def __init__(self, message: str, report: DiagnosisReport | None = None) -> None:
        """Initialize with a message and optional report.

        Args:
            message: Human-readable description of the budget violation.
            report: The DiagnosisReport from the function execution.
        """
        super().__init__(message)
        self.report = report
