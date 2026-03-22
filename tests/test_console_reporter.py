"""Tests for console reporter in query_doctor.reporters.console."""

from __future__ import annotations

import pytest

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


class TestConsoleReporterPlainText:
    """Tests for the plain-text fallback rendering path."""

    def _make_prescription(
        self,
        severity: Severity = Severity.CRITICAL,
        issue_type: IssueType = IssueType.N_PLUS_ONE,
        description: str = "N+1 detected",
        fix: str = "select_related('author')",
        callsite: CallSite | None = None,
        query_count: int = 0,
        time_saved_ms: float = 0.0,
    ) -> Prescription:
        return Prescription(
            issue_type=issue_type,
            severity=severity,
            description=description,
            fix_suggestion=fix,
            callsite=callsite,
            query_count=query_count,
            time_saved_ms=time_saved_ms,
        )

    def test_plain_fallback_renders_with_prescription(self) -> None:
        """Plain text fallback path renders when Rich import fails."""
        from unittest.mock import patch

        reporter = ConsoleReporter()
        report = DiagnosisReport(
            prescriptions=[self._make_prescription()],
            total_queries=10,
            total_time_ms=50.0,
        )
        with patch(
            "query_doctor.reporters.console.ConsoleReporter._render_rich",
            side_effect=ImportError("No rich"),
        ):
            output = reporter.render(report)

        assert "CRITICAL" in output
        assert "N+1 detected" in output
        assert "select_related" in output

    def test_plain_empty_report_shows_no_issues(self) -> None:
        """Plain text path shows 'No issues detected' for empty report."""
        from unittest.mock import patch

        reporter = ConsoleReporter()
        report = DiagnosisReport(total_queries=5, total_time_ms=10.0)
        with patch(
            "query_doctor.reporters.console.ConsoleReporter._render_rich",
            side_effect=ImportError("No rich"),
        ):
            output = reporter.render(report)

        assert "No issues detected" in output

    def test_plain_severity_labels(self) -> None:
        """Plain text shows correct severity labels for each level."""
        from unittest.mock import patch

        prescriptions = [
            self._make_prescription(severity=Severity.CRITICAL, description="crit issue"),
            self._make_prescription(severity=Severity.WARNING, description="warn issue"),
            self._make_prescription(severity=Severity.INFO, description="info issue"),
        ]
        reporter = ConsoleReporter()
        report = DiagnosisReport(
            prescriptions=prescriptions, total_queries=30, total_time_ms=100.0
        )
        with patch(
            "query_doctor.reporters.console.ConsoleReporter._render_rich",
            side_effect=ImportError("No rich"),
        ):
            output = reporter.render(report)

        assert "CRITICAL" in output
        assert "WARNING" in output
        assert "INFO" in output

    def test_plain_contains_fix_suggestion(self) -> None:
        """Plain text output includes the fix suggestion."""
        from unittest.mock import patch

        reporter = ConsoleReporter()
        report = DiagnosisReport(
            prescriptions=[self._make_prescription(fix="Add .prefetch_related('tags')")],
            total_queries=5,
            total_time_ms=10.0,
        )
        with patch(
            "query_doctor.reporters.console.ConsoleReporter._render_rich",
            side_effect=ImportError("No rich"),
        ):
            output = reporter.render(report)

        assert "prefetch_related" in output

    def test_plain_contains_callsite(self) -> None:
        """Plain text shows file:line and function from callsite."""
        from unittest.mock import patch

        cs = CallSite(
            filepath="myapp/views.py",
            line_number=42,
            function_name="list_books",
            code_context="qs = Book.objects.all()",
        )
        reporter = ConsoleReporter()
        report = DiagnosisReport(
            prescriptions=[self._make_prescription(callsite=cs)],
            total_queries=5,
            total_time_ms=10.0,
        )
        with patch(
            "query_doctor.reporters.console.ConsoleReporter._render_rich",
            side_effect=ImportError("No rich"),
        ):
            output = reporter.render(report)

        assert "myapp/views.py" in output
        assert "42" in output
        assert "list_books" in output
        assert "Book.objects.all()" in output

    def test_plain_shows_query_count_and_savings(self) -> None:
        """Plain text shows query count and estimated savings."""
        from unittest.mock import patch

        reporter = ConsoleReporter()
        report = DiagnosisReport(
            prescriptions=[self._make_prescription(query_count=47, time_saved_ms=89.0)],
            total_queries=53,
            total_time_ms=127.3,
        )
        with patch(
            "query_doctor.reporters.console.ConsoleReporter._render_rich",
            side_effect=ImportError("No rich"),
        ):
            output = reporter.render(report)

        assert "47" in output
        assert "89.0" in output

    def test_plain_issue_type_in_description(self) -> None:
        """Plain text renders the description which includes issue type info."""
        from unittest.mock import patch

        reporter = ConsoleReporter()
        report = DiagnosisReport(
            prescriptions=[
                self._make_prescription(
                    issue_type=IssueType.DUPLICATE_QUERY,
                    severity=Severity.WARNING,
                    description='Duplicate query: 6 identical queries for "publisher"',
                )
            ],
            total_queries=10,
            total_time_ms=20.0,
        )
        with patch(
            "query_doctor.reporters.console.ConsoleReporter._render_rich",
            side_effect=ImportError("No rich"),
        ):
            output = reporter.render(report)

        assert "Duplicate query" in output
        assert "publisher" in output


class TestConsoleReporterRichPath:
    """Tests for the Rich rendering path."""

    def test_rich_renders_nonempty_string(self) -> None:
        """Rich rendering path returns a non-empty string."""
        reporter = ConsoleReporter()
        report = DiagnosisReport(
            prescriptions=[
                Prescription(
                    issue_type=IssueType.N_PLUS_ONE,
                    severity=Severity.CRITICAL,
                    description="N+1 for author",
                    fix_suggestion="select_related('author')",
                    callsite=CallSite(
                        filepath="views.py",
                        line_number=10,
                        function_name="get_qs",
                        code_context="Book.objects.all()",
                    ),
                    query_count=20,
                    time_saved_ms=50.0,
                ),
            ],
            total_queries=25,
            total_time_ms=80.0,
        )
        try:
            output = reporter._render_rich(report)
            assert len(output) > 0
            assert "author" in output
        except ImportError:
            pytest.skip("Rich not installed")

    def test_rich_empty_report(self) -> None:
        """Rich rendering with no prescriptions shows no issues."""
        reporter = ConsoleReporter()
        report = DiagnosisReport(total_queries=0, total_time_ms=0.0)
        try:
            output = reporter._render_rich(report)
            assert "No issues" in output or "0" in output
        except ImportError:
            pytest.skip("Rich not installed")

    def test_rich_warning_severity(self) -> None:
        """Rich rendering applies yellow style for WARNING severity."""
        reporter = ConsoleReporter()
        report = DiagnosisReport(
            prescriptions=[
                Prescription(
                    issue_type=IssueType.DUPLICATE_QUERY,
                    severity=Severity.WARNING,
                    description="Dup query",
                    fix_suggestion="Cache result",
                    callsite=None,
                    query_count=3,
                ),
            ],
            total_queries=5,
            total_time_ms=10.0,
        )
        try:
            output = reporter._render_rich(report)
            assert "WARNING" in output
        except ImportError:
            pytest.skip("Rich not installed")

    def test_rich_info_severity(self) -> None:
        """Rich rendering handles INFO severity."""
        reporter = ConsoleReporter()
        report = DiagnosisReport(
            prescriptions=[
                Prescription(
                    issue_type=IssueType.MISSING_INDEX,
                    severity=Severity.INFO,
                    description="Missing index on published_date",
                    fix_suggestion="Add index",
                    callsite=None,
                ),
            ],
            total_queries=2,
            total_time_ms=5.0,
        )
        try:
            output = reporter._render_rich(report)
            assert "INFO" in output
        except ImportError:
            pytest.skip("Rich not installed")


class TestConsoleReporterGrouped:
    """Tests for the grouped rendering path."""

    def test_grouped_renders_groups(self) -> None:
        """Grouped mode renders group headers."""
        import io

        stream = io.StringIO()
        reporter = ConsoleReporter(stream=stream, group_by="file_analyzer")
        report = DiagnosisReport(
            prescriptions=[
                Prescription(
                    issue_type=IssueType.N_PLUS_ONE,
                    severity=Severity.CRITICAL,
                    description="N+1 for author",
                    fix_suggestion="select_related('author')",
                    callsite=CallSite(filepath="views.py", line_number=10, function_name="get_qs"),
                ),
                Prescription(
                    issue_type=IssueType.N_PLUS_ONE,
                    severity=Severity.CRITICAL,
                    description="N+1 for publisher",
                    fix_suggestion="select_related('publisher')",
                    callsite=CallSite(filepath="views.py", line_number=20, function_name="get_qs"),
                ),
            ],
            total_queries=50,
            total_time_ms=100.0,
        )
        reporter.report(report)
        output = stream.getvalue()
        assert "grouped" in output.lower()
        assert "CRITICAL" in output

    def test_grouped_empty_report(self) -> None:
        """Grouped mode with no prescriptions shows no issues."""
        import io

        stream = io.StringIO()
        reporter = ConsoleReporter(stream=stream, group_by="root_cause")
        report = DiagnosisReport(total_queries=0, total_time_ms=0.0)
        reporter.report(report)
        output = stream.getvalue()
        assert "No issues detected" in output
