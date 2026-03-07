"""Tests for public API exports in query_doctor.__init__."""

from __future__ import annotations


class TestPublicAPI:
    """Tests for the public API surface."""

    def test_import_diagnose_queries(self) -> None:
        """diagnose_queries should be importable from query_doctor."""
        from query_doctor import diagnose_queries

        assert callable(diagnose_queries)

    def test_import_middleware(self) -> None:
        """QueryDoctorMiddleware should be importable from query_doctor."""
        from query_doctor import QueryDoctorMiddleware

        assert QueryDoctorMiddleware is not None

    def test_import_types(self) -> None:
        """Core types should be importable from query_doctor."""
        from query_doctor import DiagnosisReport, Prescription

        assert DiagnosisReport is not None
        assert Prescription is not None

    def test_import_severity_and_issue_type(self) -> None:
        """Enums should be importable from query_doctor."""
        from query_doctor import IssueType, Severity

        assert Severity.CRITICAL is not None
        assert IssueType.N_PLUS_ONE is not None
