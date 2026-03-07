"""Tests for console reporter in query_doctor.reporters.console."""

from __future__ import annotations

from query_doctor.reporters.console import ConsoleReporter
from query_doctor.types import (
    CallSite,
    DiagnosisReport,
    IssueType,
    Prescription,
    Severity,
)


class TestConsoleReporter:
    """Tests for ConsoleReporter."""

    def test_render_empty_report(self) -> None:
        """Empty report should still produce output."""
        reporter = ConsoleReporter()
        report = DiagnosisReport()
        output = reporter.render(report)
        assert "0" in output  # Should mention 0 queries or 0 issues

    def test_render_report_with_nplusone(self) -> None:
        """Report with N+1 prescription should show CRITICAL label."""
        reporter = ConsoleReporter()
        report = DiagnosisReport(
            prescriptions=[
                Prescription(
                    issue_type=IssueType.N_PLUS_ONE,
                    severity=Severity.CRITICAL,
                    description='N+1 detected: 47 queries for table "testapp_author"',
                    fix_suggestion="Add .select_related('author') to your queryset",
                    callsite=CallSite(
                        filepath="myapp/views.py",
                        line_number=83,
                        function_name="get_queryset",
                    ),
                    query_count=47,
                    time_saved_ms=89.0,
                ),
            ],
            total_queries=53,
            total_time_ms=127.3,
        )
        output = reporter.render(report)
        assert "CRITICAL" in output
        assert "N+1" in output or "n+1" in output.lower()
        assert "select_related" in output
        assert "author" in output
        assert "myapp/views.py" in output

    def test_render_report_with_duplicate(self) -> None:
        """Report with duplicate prescription should show WARNING label."""
        reporter = ConsoleReporter()
        report = DiagnosisReport(
            prescriptions=[
                Prescription(
                    issue_type=IssueType.DUPLICATE_QUERY,
                    severity=Severity.WARNING,
                    description='6 identical queries for table "testapp_publisher"',
                    fix_suggestion="Assign the queryset result to a variable",
                    callsite=None,
                    query_count=6,
                ),
            ],
            total_queries=10,
            total_time_ms=5.0,
        )
        output = reporter.render(report)
        assert "WARNING" in output
        assert "identical" in output.lower()

    def test_render_includes_summary(self) -> None:
        """Report should include query count and time summary."""
        reporter = ConsoleReporter()
        report = DiagnosisReport(
            total_queries=53,
            total_time_ms=127.3,
        )
        output = reporter.render(report)
        assert "53" in output
        assert "127.3" in output or "127" in output

    def test_render_multiple_prescriptions(self) -> None:
        """Report with multiple prescriptions should render all of them."""
        reporter = ConsoleReporter()
        report = DiagnosisReport(
            prescriptions=[
                Prescription(
                    issue_type=IssueType.N_PLUS_ONE,
                    severity=Severity.CRITICAL,
                    description="N+1 for author",
                    fix_suggestion="select_related('author')",
                    callsite=None,
                    query_count=10,
                ),
                Prescription(
                    issue_type=IssueType.DUPLICATE_QUERY,
                    severity=Severity.WARNING,
                    description="Duplicate publisher queries",
                    fix_suggestion="Cache the result",
                    callsite=None,
                    query_count=5,
                ),
            ],
            total_queries=20,
            total_time_ms=50.0,
        )
        output = reporter.render(report)
        assert "author" in output
        assert "publisher" in output.lower() or "Duplicate" in output

    def test_render_with_callsite(self) -> None:
        """Prescription with callsite should show file:line."""
        reporter = ConsoleReporter()
        report = DiagnosisReport(
            prescriptions=[
                Prescription(
                    issue_type=IssueType.N_PLUS_ONE,
                    severity=Severity.WARNING,
                    description="N+1",
                    fix_suggestion="Fix it",
                    callsite=CallSite(
                        filepath="myapp/views.py",
                        line_number=42,
                        function_name="my_view",
                        code_context="books = Book.objects.all()",
                    ),
                ),
            ],
        )
        output = reporter.render(report)
        assert "myapp/views.py" in output
        assert "42" in output

    def test_report_method_prints(self, capsys) -> None:
        """report() should print to stderr."""
        reporter = ConsoleReporter()
        report = DiagnosisReport(total_queries=5)
        reporter.report(report)
        captured = capsys.readouterr()
        assert "5" in captured.err
