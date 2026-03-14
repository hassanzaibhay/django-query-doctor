"""Tests for project report generators."""

from __future__ import annotations

import json

from query_doctor.project_diagnoser import (
    AppDiagnosisResult,
    ProjectDiagnosisResult,
    URLDiagnosisResult,
)
from query_doctor.reporters.project_report import (
    ProjectJsonReporter,
    ProjectReportGenerator,
)
from query_doctor.types import (
    CallSite,
    DiagnosisReport,
    IssueType,
    Prescription,
    Severity,
)
from query_doctor.url_discovery import DiscoveredURL


def _make_url(
    pattern: str = "/api/books/",
    app_name: str = "myapp",
) -> DiscoveredURL:
    return DiscoveredURL(
        pattern=pattern,
        name="books",
        app_name=app_name,
        view_name="BookListView",
        methods=["GET"],
        has_parameters=False,
    )


def _make_result_with_issues() -> ProjectDiagnosisResult:
    """Create a project result with some issues for testing."""
    report = DiagnosisReport(total_queries=10, total_time_ms=50.0)
    report.prescriptions.append(
        Prescription(
            issue_type=IssueType.N_PLUS_ONE,
            severity=Severity.CRITICAL,
            description='N+1 detected: 10 queries for "author"',
            fix_suggestion="Add .select_related('author')",
            callsite=CallSite(
                filepath="myapp/views.py",
                line_number=42,
                function_name="get_queryset",
                code_context="Book.objects.all()",
            ),
            query_count=10,
        )
    )

    url_result = URLDiagnosisResult(
        url=_make_url(),
        report=report,
        status_code=200,
        duration_ms=100.0,
    )

    app = AppDiagnosisResult(app_name="myapp")
    app.url_results.append(url_result)

    result = ProjectDiagnosisResult(
        started_at="2026-03-15T10:00:00",
        finished_at="2026-03-15T10:00:30",
    )
    result.app_results.append(app)
    return result


class TestProjectReportGenerator:
    """Tests for HTML report generation."""

    def test_generates_html(self) -> None:
        """Report generates valid HTML."""
        result = _make_result_with_issues()
        html = ProjectReportGenerator().generate(result)
        assert "<!DOCTYPE html>" in html
        assert "</html>" in html

    def test_contains_executive_summary(self) -> None:
        """HTML report contains executive summary section."""
        result = _make_result_with_issues()
        html = ProjectReportGenerator().generate(result)
        assert "Executive Summary" in html

    def test_contains_app_scoreboard(self) -> None:
        """HTML report contains app scoreboard."""
        result = _make_result_with_issues()
        html = ProjectReportGenerator().generate(result)
        assert "myapp" in html

    def test_contains_prescription_detail(self) -> None:
        """HTML report contains prescription details."""
        result = _make_result_with_issues()
        html = ProjectReportGenerator().generate(result)
        assert "N+1" in html
        assert "select_related" in html

    def test_contains_skipped_urls(self) -> None:
        """HTML report contains skipped URLs section."""
        result = _make_result_with_issues()
        result.skipped_urls.append(("/admin/", "excluded by pattern"))
        html = ProjectReportGenerator().generate(result)
        assert "Skipped" in html

    def test_empty_project_valid_html(self) -> None:
        """Empty project produces valid HTML report."""
        result = ProjectDiagnosisResult(
            started_at="2026-03-15T10:00:00",
            finished_at="2026-03-15T10:00:01",
        )
        html = ProjectReportGenerator().generate(result)
        assert "<!DOCTYPE html>" in html
        assert "</html>" in html

    def test_no_issues_shows_healthy(self) -> None:
        """Report with no issues shows healthy score."""
        result = ProjectDiagnosisResult(
            started_at="2026-03-15T10:00:00",
            finished_at="2026-03-15T10:00:01",
        )
        app = AppDiagnosisResult(app_name="clean_app")
        url_result = URLDiagnosisResult(
            url=_make_url(app_name="clean_app"),
            report=DiagnosisReport(total_queries=5, total_time_ms=10.0),
            status_code=200,
        )
        app.url_results.append(url_result)
        result.app_results.append(app)

        html = ProjectReportGenerator().generate(result)
        assert "100" in html


class TestProjectJsonReporter:
    """Tests for JSON report generation."""

    def test_generates_valid_json(self) -> None:
        """JSON report is valid JSON."""
        result = _make_result_with_issues()
        output = ProjectJsonReporter().generate(result)
        data = json.loads(output)
        assert isinstance(data, dict)

    def test_json_has_expected_structure(self) -> None:
        """JSON report has the expected top-level keys."""
        result = _make_result_with_issues()
        output = ProjectJsonReporter().generate(result)
        data = json.loads(output)
        assert "summary" in data
        assert "apps" in data
        assert "started_at" in data

    def test_json_summary_fields(self) -> None:
        """JSON summary has correct aggregate fields."""
        result = _make_result_with_issues()
        output = ProjectJsonReporter().generate(result)
        data = json.loads(output)
        summary = data["summary"]
        assert "total_urls" in summary
        assert "total_queries" in summary
        assert "total_issues" in summary
        assert "health_score" in summary

    def test_json_empty_project(self) -> None:
        """Empty project produces valid JSON."""
        result = ProjectDiagnosisResult(
            started_at="2026-03-15T10:00:00",
            finished_at="2026-03-15T10:00:01",
        )
        output = ProjectJsonReporter().generate(result)
        data = json.loads(output)
        assert data["summary"]["total_urls"] == 0
