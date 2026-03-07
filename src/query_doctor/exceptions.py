"""Exception hierarchy for django-query-doctor.

All package exceptions inherit from QueryDoctorError to allow
callers to catch any query-doctor-specific error with a single except clause.
"""
from __future__ import annotations


class QueryDoctorError(Exception):
    """Base exception for all django-query-doctor errors."""


class ConfigError(QueryDoctorError):
    """Raised when there is a configuration error."""


class AnalyzerError(QueryDoctorError):
    """Raised when an analyzer encounters an error."""


class InterceptorError(QueryDoctorError):
    """Raised when the query interceptor encounters an error."""
