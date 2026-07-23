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

    def test_import_diagnose_decorator(self) -> None:
        """@diagnose should be importable from query_doctor."""
        from query_doctor import diagnose

        assert callable(diagnose)

    def test_import_query_budget_decorator(self) -> None:
        """@query_budget should be importable from query_doctor."""
        from query_doctor import query_budget

        assert callable(query_budget)

    def test_import_query_budget_error(self) -> None:
        """QueryBudgetError should be importable from query_doctor."""
        from query_doctor import QueryBudgetError

        assert issubclass(QueryBudgetError, Exception)

    def test_import_captured_query(self) -> None:
        """CapturedQuery should be importable from query_doctor."""
        from query_doctor import CapturedQuery

        assert CapturedQuery is not None

    def test_import_callsite(self) -> None:
        """CallSite should be importable from query_doctor."""
        from query_doctor import CallSite

        assert CallSite is not None

    def test_version(self) -> None:
        """__version__ must exist and must agree with the installed distribution metadata.

        Two assertions, deliberately: the first fails informatively when the attribute is
        removed or emptied, the second when the runtime version and the distribution
        metadata drift apart. A hardcoded literal here -- what this test used to compare
        against -- was a third place a release had to remember to edit, and it could not
        detect the drift it looked like it was guarding (FOLLOWUPS.md item 16).
        """
        import importlib.metadata

        import query_doctor

        assert isinstance(query_doctor.__version__, str)
        assert query_doctor.__version__

        assert query_doctor.__version__ == importlib.metadata.version("django-query-doctor"), (
            "runtime __version__ and installed distribution metadata disagree. Distribution "
            "metadata is snapshotted at install time, so after bumping "
            'src/query_doctor/__init__.py you must re-run `pip install -e "."` before the '
            "suite will pass."
        )
