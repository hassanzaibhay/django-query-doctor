"""Tests for the HTML reporter.

Verifies generation of standalone HTML reports with summary,
prescriptions, and inline CSS styling.
"""

from __future__ import annotations

import os
import tempfile

from query_doctor.reporters.html_reporter import HTMLReporter
from query_doctor.types import (
    CallSite,
    DiagnosisReport,
    IssueType,
    Prescription,
    Severity,
)


def _make_report(
    prescriptions: list[Prescription] | None = None,
    total_queries: int = 10,
    total_time_ms: float = 50.0,
) -> DiagnosisReport:
    """Create a test DiagnosisReport."""
    return DiagnosisReport(
        prescriptions=prescriptions or [],
        total_queries=total_queries,
        total_time_ms=total_time_ms,
    )


def _make_prescription(
    severity: Severity = Severity.WARNING,
    description: str = "Test issue",
    fix: str = "Test fix",
    callsite: CallSite | None = None,
    query_count: int = 5,
    time_saved_ms: float = 10.0,
) -> Prescription:
    """Create a test Prescription."""
    return Prescription(
        issue_type=IssueType.N_PLUS_ONE,
        severity=severity,
        description=description,
        fix_suggestion=fix,
        callsite=callsite,
        query_count=query_count,
        time_saved_ms=time_saved_ms,
    )


class TestHTMLRender:
    """Tests for HTML rendering output."""

    def test_render_returns_html_string(self) -> None:
        """render() should return a valid HTML string."""
        reporter = HTMLReporter()
        report = _make_report()

        html = reporter.render(report)

        assert "<html" in html
        assert "</html>" in html

    def test_contains_inline_css(self) -> None:
        """HTML should contain inline CSS styles."""
        reporter = HTMLReporter()
        report = _make_report()

        html = reporter.render(report)

        assert "<style>" in html

    def test_contains_summary(self) -> None:
        """HTML should contain the report summary."""
        reporter = HTMLReporter()
        report = _make_report(total_queries=42, total_time_ms=123.4)

        html = reporter.render(report)

        assert "42" in html
        assert "123.4" in html

    def test_contains_prescriptions(self) -> None:
        """HTML should list all prescriptions."""
        prescriptions = [
            _make_prescription(description="N+1 issue found"),
            _make_prescription(
                severity=Severity.CRITICAL,
                description="Critical duplicate",
            ),
        ]
        reporter = HTMLReporter()
        report = _make_report(prescriptions=prescriptions)

        html = reporter.render(report)

        assert "N+1 issue found" in html
        assert "Critical duplicate" in html

    def test_contains_fix_suggestions(self) -> None:
        """HTML should include fix suggestions."""
        p = _make_prescription(fix="Add .select_related('author')")
        reporter = HTMLReporter()
        report = _make_report(prescriptions=[p])

        html = reporter.render(report)

        assert "select_related" in html

    def test_contains_callsite(self) -> None:
        """HTML should display call site info when available."""
        cs = CallSite(
            filepath="myapp/views.py",
            line_number=42,
            function_name="get_queryset",
            code_context="books = Book.objects.all()",
        )
        p = _make_prescription(callsite=cs)
        reporter = HTMLReporter()
        report = _make_report(prescriptions=[p])

        html = reporter.render(report)

        assert "myapp/views.py" in html
        assert "42" in html
        assert "get_queryset" in html

    def test_no_issues_message(self) -> None:
        """HTML should show a positive message when no issues found."""
        reporter = HTMLReporter()
        report = _make_report(prescriptions=[])

        html = reporter.render(report)

        assert "No issues" in html or "no issues" in html.lower()

    def test_severity_styling(self) -> None:
        """Different severities should have distinct visual markers."""
        prescriptions = [
            _make_prescription(severity=Severity.CRITICAL, description="Crit"),
            _make_prescription(severity=Severity.WARNING, description="Warn"),
            _make_prescription(severity=Severity.INFO, description="Info"),
        ]
        reporter = HTMLReporter()
        report = _make_report(prescriptions=prescriptions)

        html = reporter.render(report)

        assert "CRITICAL" in html
        assert "WARNING" in html
        assert "INFO" in html


class TestHTMLFileOutput:
    """Tests for writing HTML to files."""

    def test_report_writes_file(self) -> None:
        """report() with output_path should write the HTML file."""
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as f:
            path = f.name

        try:
            reporter = HTMLReporter(output_path=path)
            report = _make_report(total_queries=7)
            reporter.report(report)

            with open(path, encoding="utf-8") as fh:
                content = fh.read()

            assert "<html" in content
            assert "7" in content
        finally:
            os.unlink(path)

    def test_report_without_output_path(self) -> None:
        """report() without output_path should not crash."""
        reporter = HTMLReporter()
        report = _make_report()
        reporter.report(report)

    def test_report_with_invalid_path(self) -> None:
        """report() with invalid path should not crash."""
        reporter = HTMLReporter(output_path="/nonexistent/dir/report.html")
        report = _make_report()
        # Should not raise
        reporter.report(report)


class TestHTMLEdgeCases:
    """Edge cases for HTML reporter."""

    def test_escapes_html_in_descriptions(self) -> None:
        """HTML special characters in descriptions should be escaped."""
        p = _make_prescription(description='<script>alert("xss")</script>')
        reporter = HTMLReporter()
        report = _make_report(prescriptions=[p])

        html = reporter.render(report)

        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_escapes_html_in_fix(self) -> None:
        """HTML special characters in fix suggestions should be escaped."""
        p = _make_prescription(fix="Use <b>bold</b>")
        reporter = HTMLReporter()
        report = _make_report(prescriptions=[p])

        html = reporter.render(report)

        assert "<b>bold</b>" not in html

    def test_large_report(self) -> None:
        """Should handle reports with many prescriptions."""
        prescriptions = [_make_prescription(description=f"Issue #{i}") for i in range(50)]
        reporter = HTMLReporter()
        report = _make_report(prescriptions=prescriptions)

        html = reporter.render(report)

        assert "Issue #0" in html
        assert "Issue #49" in html
