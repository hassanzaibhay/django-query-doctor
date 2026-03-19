"""Prescription filtering utilities for django-query-doctor.

Provides post-collection filters that narrow down prescriptions by
file path, module name, or other criteria before reporting.
"""

from __future__ import annotations

from query_doctor.filters.file_filter import PrescriptionFilter

__all__ = ["PrescriptionFilter"]
