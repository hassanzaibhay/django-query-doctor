"""django-query-doctor: Automated diagnosis and prescriptions for slow Django ORM queries."""
from __future__ import annotations

from query_doctor.context_managers import diagnose_queries
from query_doctor.middleware import QueryDoctorMiddleware
from query_doctor.types import (
    DiagnosisReport,
    IssueType,
    Prescription,
    Severity,
)

__all__ = [
    "DiagnosisReport",
    "IssueType",
    "Prescription",
    "QueryDoctorMiddleware",
    "Severity",
    "diagnose_queries",
]
