"""Tests for the JSON reporter.

Verifies that the JSON reporter produces valid, structured JSON output
matching the expected schema, and correctly writes to files.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from query_doctor.reporters.json_reporter import JSONReporter
from query_doctor.types import (
    CallSite,
    DiagnosisReport,
    IssueType,
    Prescription,
    Severity,
)


def _make_report(
    prescriptions: list[Prescription] | None = None,
    total_queries: int = 53,
    total_time_ms: float = 127.3,
) -> DiagnosisReport:
    """Helper to create a DiagnosisReport for testing."""
    return DiagnosisReport(
        prescriptions=prescriptions or [],
        total_queries=total_queries,
        total_time_ms=total_time_ms,
    )


def _make_prescription(
    issue_type: IssueType = IssueType.N_PLUS_ONE,
    severity: Severity = Severity.CRITICAL,
    query_count: int = 47,
    time_saved_ms: float = 89.2,
) -> Prescription:
    """Helper to create a Prescription for testing."""
    return Prescription(
        issue_type=issue_type,
        severity=severity,
        description=f"Test {issue_type.value} issue",
        fix_suggestion="Add .select_related('author') to queryset",
        callsite=CallSite(
            filepath="views.py",
            line_number=83,
            function_name="get_queryset",
        ),
        query_count=query_count,
        time_saved_ms=time_saved_ms,
        fingerprint="abc123",
    )


class TestJSONReporter:
    """Tests for JSONReporter."""

    def test_render_returns_valid_json(self) -> None:
        """Rendered output should be valid JSON."""
        reporter = JSONReporter()
        report = _make_report(prescriptions=[_make_prescription()])
        output = reporter.render(report)
        data = json.loads(output)
        assert isinstance(data, dict)

    def test_json_structure_has_version(self) -> None:
        """JSON output should include a version field."""
        reporter = JSONReporter()
        report = _make_report()
        data = json.loads(reporter.render(report))
        assert "version" in data

    def test_json_structure_has_timestamp(self) -> None:
        """JSON output should include a timestamp field."""
        reporter = JSONReporter()
        report = _make_report()
        data = json.loads(reporter.render(report))
        assert "timestamp" in data

    def test_json_structure_has_summary(self) -> None:
        """JSON output should include a summary section."""
        reporter = JSONReporter()
        rx = _make_prescription()
        report = _make_report(prescriptions=[rx])
        data = json.loads(reporter.render(report))
        summary = data["summary"]
        assert summary["total_queries"] == 53
        assert summary["total_time_ms"] == 127.3
        assert summary["issues_found"] == 1
        assert summary["critical"] == 1
        assert summary["warnings"] == 0
        assert summary["info"] == 0

    def test_json_prescriptions_structure(self) -> None:
        """Each prescription in JSON should have the expected fields."""
        reporter = JSONReporter()
        rx = _make_prescription()
        report = _make_report(prescriptions=[rx])
        data = json.loads(reporter.render(report))
        assert len(data["prescriptions"]) == 1
        p = data["prescriptions"][0]
        assert p["issue_type"] == "n_plus_one"
        assert p["severity"] == "critical"
        assert "description" in p
        assert "fix_suggestion" in p
        assert p["query_count"] == 47
        assert p["estimated_savings_ms"] == 89.2

    def test_json_prescription_location(self) -> None:
        """Prescription location should include file, line, and function."""
        reporter = JSONReporter()
        rx = _make_prescription()
        report = _make_report(prescriptions=[rx])
        data = json.loads(reporter.render(report))
        loc = data["prescriptions"][0]["location"]
        assert loc["file"] == "views.py"
        assert loc["line"] == 83
        assert loc["function"] == "get_queryset"

    def test_empty_report(self) -> None:
        """Empty report should produce valid JSON with zero issues."""
        reporter = JSONReporter()
        report = _make_report(total_queries=0, total_time_ms=0.0)
        data = json.loads(reporter.render(report))
        assert data["summary"]["issues_found"] == 0
        assert data["prescriptions"] == []

    def test_multiple_prescriptions(self) -> None:
        """Multiple prescriptions should all appear in JSON."""
        reporter = JSONReporter()
        prescriptions = [
            _make_prescription(severity=Severity.CRITICAL),
            _make_prescription(
                issue_type=IssueType.DUPLICATE_QUERY,
                severity=Severity.WARNING,
            ),
            _make_prescription(
                issue_type=IssueType.MISSING_INDEX,
                severity=Severity.INFO,
            ),
        ]
        report = _make_report(prescriptions=prescriptions)
        data = json.loads(reporter.render(report))
        assert data["summary"]["critical"] == 1
        assert data["summary"]["warnings"] == 1
        assert data["summary"]["info"] == 1
        assert len(data["prescriptions"]) == 3

    def test_write_to_file(self) -> None:
        """Reporter should write JSON to a file when path is configured."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "report.json"
            reporter = JSONReporter(output_path=str(filepath))
            report = _make_report(prescriptions=[_make_prescription()])
            reporter.report(report)

            assert filepath.exists()
            data = json.loads(filepath.read_text())
            assert data["summary"]["issues_found"] == 1

    def test_report_without_file_path(self) -> None:
        """Reporter without output_path should not crash."""
        reporter = JSONReporter()
        report = _make_report(prescriptions=[_make_prescription()])
        # Should not raise — just renders internally
        reporter.report(report)

    def test_prescription_without_callsite(self) -> None:
        """Prescription without callsite should have null location."""
        reporter = JSONReporter()
        rx = Prescription(
            issue_type=IssueType.DUPLICATE_QUERY,
            severity=Severity.WARNING,
            description="Duplicate query detected",
            fix_suggestion="Cache the result",
            callsite=None,
            query_count=5,
        )
        report = _make_report(prescriptions=[rx])
        data = json.loads(reporter.render(report))
        assert data["prescriptions"][0]["location"] is None
