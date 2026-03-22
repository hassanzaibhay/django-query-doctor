"""Tests for GitHub Actions CI integration."""

from __future__ import annotations

import io
import json

from query_doctor.ci.github import (
    format_github_annotations,
    generate_pr_comment,
    write_json_report,
)
from query_doctor.types import (
    CallSite,
    DiagnosisReport,
    IssueType,
    Prescription,
    Severity,
)


def _make_report(n_issues: int = 0) -> DiagnosisReport:
    """Create a test report with n prescriptions."""
    report = DiagnosisReport(total_queries=10, total_time_ms=50.0)
    for i in range(n_issues):
        report.prescriptions.append(
            Prescription(
                issue_type=IssueType.N_PLUS_ONE,
                severity=Severity.CRITICAL if i == 0 else Severity.WARNING,
                description=f"Issue {i + 1}",
                fix_suggestion=f"Fix {i + 1}",
                callsite=CallSite(
                    filepath="myapp/views.py",
                    line_number=10 + i,
                    function_name="get_queryset",
                ),
                query_count=5,
            )
        )
    return report


class TestGitHubAnnotations:
    """GitHub Actions annotation output."""

    def test_annotations_empty(self):
        """No prescriptions → no annotations."""
        stream = io.StringIO()
        format_github_annotations([], stream=stream)
        assert stream.getvalue() == ""

    def test_annotations_critical(self):
        """Critical issues use ::error level."""
        report = _make_report(1)
        stream = io.StringIO()
        format_github_annotations(report.prescriptions, stream=stream)
        output = stream.getvalue()
        assert "::error" in output
        assert "myapp/views.py" in output

    def test_annotations_warning(self):
        """Warning issues use ::warning level."""
        p = Prescription(
            issue_type=IssueType.DUPLICATE_QUERY,
            severity=Severity.WARNING,
            description="Dup query",
            fix_suggestion="Cache it",
            callsite=CallSite(filepath="views.py", line_number=5, function_name="f"),
        )
        stream = io.StringIO()
        format_github_annotations([p], stream=stream)
        assert "::warning" in stream.getvalue()


class TestPRComment:
    """PR comment Markdown generation."""

    def test_clean_report(self):
        """No issues → success message."""
        report = _make_report(0)
        comment = generate_pr_comment(report)
        assert "No query issues found" in comment
        assert "Clean bill of health" in comment

    def test_issues_report(self):
        """Issues → markdown summary with details."""
        report = _make_report(2)
        comment = generate_pr_comment(report)
        assert "2" in comment
        assert "CRITICAL" in comment
        assert "How to fix" in comment

    def test_contains_file_references(self):
        """PR comment includes file:line references."""
        report = _make_report(1)
        comment = generate_pr_comment(report)
        assert "myapp/views.py:10" in comment


class TestJsonReport:
    """JSON file output for CI consumption."""

    def test_write_json(self, tmp_path):
        """Writes valid JSON file with expected structure."""
        report = _make_report(2)
        path = str(tmp_path / "report.json")
        write_json_report(report, path)

        data = json.loads((tmp_path / "report.json").read_text())
        assert len(data) == 2
        assert data[0]["severity"] == "critical"
        assert data[0]["file"] == "myapp/views.py"
        assert data[0]["suggestion"] == "Fix 1"

    def test_write_empty_report(self, tmp_path):
        """Empty report writes empty JSON array."""
        report = _make_report(0)
        path = str(tmp_path / "empty.json")
        write_json_report(report, path)

        data = json.loads((tmp_path / "empty.json").read_text())
        assert data == []
