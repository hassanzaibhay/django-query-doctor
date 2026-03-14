"""Tests for core data structures in query_doctor.types."""

from __future__ import annotations

from query_doctor.types import (
    CallSite,
    CapturedQuery,
    DiagnosisReport,
    IssueType,
    Prescription,
    Severity,
)


class TestSeverity:
    """Tests for Severity enum."""

    def test_severity_values(self) -> None:
        assert Severity.CRITICAL.value == "critical"
        assert Severity.WARNING.value == "warning"
        assert Severity.INFO.value == "info"

    def test_severity_members(self) -> None:
        assert len(Severity) == 3


class TestIssueType:
    """Tests for IssueType enum."""

    def test_issue_type_values(self) -> None:
        assert IssueType.N_PLUS_ONE.value == "n_plus_one"
        assert IssueType.DUPLICATE_QUERY.value == "duplicate_query"
        assert IssueType.MISSING_INDEX.value == "missing_index"
        assert IssueType.FAT_SELECT.value == "fat_select"
        assert IssueType.QUERYSET_EVAL.value == "queryset_eval"
        assert IssueType.DRF_SERIALIZER.value == "drf_serializer"

    def test_issue_type_members(self) -> None:
        assert len(IssueType) == 7


class TestCallSite:
    """Tests for CallSite dataclass."""

    def test_create_callsite(self) -> None:
        cs = CallSite(
            filepath="myapp/views.py",
            line_number=42,
            function_name="get_queryset",
            code_context="books = Book.objects.all()",
        )
        assert cs.filepath == "myapp/views.py"
        assert cs.line_number == 42
        assert cs.function_name == "get_queryset"
        assert cs.code_context == "books = Book.objects.all()"

    def test_callsite_is_frozen(self) -> None:
        cs = CallSite(filepath="x.py", line_number=1, function_name="f")
        try:
            cs.filepath = "y.py"  # type: ignore[misc]
            raise AssertionError("Should have raised FrozenInstanceError")
        except AttributeError:
            pass

    def test_callsite_default_code_context(self) -> None:
        cs = CallSite(filepath="x.py", line_number=1, function_name="f")
        assert cs.code_context == ""


class TestCapturedQuery:
    """Tests for CapturedQuery dataclass."""

    def test_create_captured_query(self) -> None:
        cq = CapturedQuery(
            sql='SELECT * FROM "testapp_book" WHERE "id" = 1',
            params=(1,),
            duration_ms=1.5,
            fingerprint="abc123",
            normalized_sql='select * from "testapp_book" where "id" = ?',
            callsite=None,
            is_select=True,
            tables=["testapp_book"],
        )
        assert cq.sql == 'SELECT * FROM "testapp_book" WHERE "id" = 1'
        assert cq.params == (1,)
        assert cq.duration_ms == 1.5
        assert cq.is_select is True
        assert cq.tables == ["testapp_book"]

    def test_captured_query_is_frozen(self) -> None:
        cq = CapturedQuery(
            sql="SELECT 1",
            params=None,
            duration_ms=0.1,
            fingerprint="x",
            normalized_sql="select ?",
            callsite=None,
            is_select=True,
            tables=[],
        )
        try:
            cq.sql = "SELECT 2"  # type: ignore[misc]
            raise AssertionError("Should have raised FrozenInstanceError")
        except AttributeError:
            pass


class TestPrescription:
    """Tests for Prescription dataclass."""

    def test_create_prescription(self) -> None:
        p = Prescription(
            issue_type=IssueType.N_PLUS_ONE,
            severity=Severity.CRITICAL,
            description="N+1 detected: 47 queries for Author",
            fix_suggestion="Add .select_related('author') to queryset",
            callsite=None,
            query_count=47,
            time_saved_ms=89.0,
            fingerprint="abc123",
        )
        assert p.issue_type == IssueType.N_PLUS_ONE
        assert p.severity == Severity.CRITICAL
        assert p.query_count == 47

    def test_prescription_defaults(self) -> None:
        p = Prescription(
            issue_type=IssueType.DUPLICATE_QUERY,
            severity=Severity.WARNING,
            description="test",
            fix_suggestion="test fix",
            callsite=None,
        )
        assert p.query_count == 0
        assert p.time_saved_ms == 0
        assert p.fingerprint == ""
        assert p.extra == {}

    def test_prescription_is_mutable(self) -> None:
        p = Prescription(
            issue_type=IssueType.N_PLUS_ONE,
            severity=Severity.WARNING,
            description="test",
            fix_suggestion="fix",
            callsite=None,
        )
        p.query_count = 10
        assert p.query_count == 10


class TestDiagnosisReport:
    """Tests for DiagnosisReport dataclass."""

    def test_empty_report(self) -> None:
        report = DiagnosisReport()
        assert report.prescriptions == []
        assert report.total_queries == 0
        assert report.total_time_ms == 0
        assert report.captured_queries == []
        assert report.issues == 0
        assert report.n_plus_one_count == 0
        assert report.has_critical is False

    def test_report_issues_count(self) -> None:
        report = DiagnosisReport(
            prescriptions=[
                Prescription(
                    issue_type=IssueType.N_PLUS_ONE,
                    severity=Severity.CRITICAL,
                    description="a",
                    fix_suggestion="b",
                    callsite=None,
                ),
                Prescription(
                    issue_type=IssueType.DUPLICATE_QUERY,
                    severity=Severity.WARNING,
                    description="c",
                    fix_suggestion="d",
                    callsite=None,
                ),
            ]
        )
        assert report.issues == 2

    def test_report_n_plus_one_count(self) -> None:
        report = DiagnosisReport(
            prescriptions=[
                Prescription(
                    issue_type=IssueType.N_PLUS_ONE,
                    severity=Severity.CRITICAL,
                    description="a",
                    fix_suggestion="b",
                    callsite=None,
                ),
                Prescription(
                    issue_type=IssueType.N_PLUS_ONE,
                    severity=Severity.WARNING,
                    description="c",
                    fix_suggestion="d",
                    callsite=None,
                ),
                Prescription(
                    issue_type=IssueType.DUPLICATE_QUERY,
                    severity=Severity.WARNING,
                    description="e",
                    fix_suggestion="f",
                    callsite=None,
                ),
            ]
        )
        assert report.n_plus_one_count == 2

    def test_report_has_critical(self) -> None:
        report = DiagnosisReport(
            prescriptions=[
                Prescription(
                    issue_type=IssueType.N_PLUS_ONE,
                    severity=Severity.CRITICAL,
                    description="a",
                    fix_suggestion="b",
                    callsite=None,
                ),
            ]
        )
        assert report.has_critical is True

    def test_report_no_critical(self) -> None:
        report = DiagnosisReport(
            prescriptions=[
                Prescription(
                    issue_type=IssueType.DUPLICATE_QUERY,
                    severity=Severity.WARNING,
                    description="a",
                    fix_suggestion="b",
                    callsite=None,
                ),
            ]
        )
        assert report.has_critical is False
