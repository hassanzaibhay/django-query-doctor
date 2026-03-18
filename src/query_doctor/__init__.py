"""django-query-doctor: Automated diagnosis and prescriptions for slow Django ORM queries."""

from __future__ import annotations

from query_doctor.context_managers import diagnose_queries
from query_doctor.decorators import diagnose, query_budget
from query_doctor.exceptions import QueryBudgetError
from query_doctor.middleware import QueryDoctorMiddleware
from query_doctor.types import (
    CallSite,
    CapturedQuery,
    DiagnosisReport,
    IssueType,
    Prescription,
    Severity,
)

__version__ = "1.0.3"

__all__ = [
    "CallSite",
    "CapturedQuery",
    "DiagnosisReport",
    "IssueType",
    "Prescription",
    "QueryBudgetError",
    "QueryDoctorMiddleware",
    "Severity",
    "diagnose",
    "diagnose_queries",
    "query_budget",
]
