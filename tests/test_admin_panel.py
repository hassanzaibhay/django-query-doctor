"""Tests for the Django admin dashboard panel."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from query_doctor.admin_panel import (
    MAX_REPORTS,
    QueryDoctorDashboardView,
    _report_buffer,
    record_report,
)
from query_doctor.types import DiagnosisReport, IssueType, Prescription, Severity


def _make_report(
    total_queries: int = 5,
    total_time_ms: float = 10.0,
    num_prescriptions: int = 1,
    has_critical: bool = False,
) -> DiagnosisReport:
    """Create a DiagnosisReport for testing."""
    prescriptions = []
    for i in range(num_prescriptions):
        prescriptions.append(
            Prescription(
                issue_type=IssueType.N_PLUS_ONE,
                severity=Severity.CRITICAL if has_critical and i == 0 else Severity.WARNING,
                description=f"Issue {i}",
                fix_suggestion=f"Fix {i}",
                callsite=None,
            )
        )
    return DiagnosisReport(
        prescriptions=prescriptions,
        total_queries=total_queries,
        total_time_ms=total_time_ms,
    )


class TestRecordReport:
    """Tests for the record_report function."""

    def setup_method(self) -> None:
        """Clear the report buffer before each test."""
        _report_buffer.clear()

    def test_record_report_stores_in_buffer(self) -> None:
        """record_report should add to the buffer."""
        report = _make_report()
        record_report("/api/books/", "GET", report)
        assert len(_report_buffer) == 1
        assert _report_buffer[0]["path"] == "/api/books/"
        assert _report_buffer[0]["method"] == "GET"
        assert _report_buffer[0]["total_queries"] == 5

    def test_buffer_respects_max_size(self) -> None:
        """Buffer should evict oldest entries when exceeding MAX_REPORTS."""
        report = _make_report()
        for i in range(MAX_REPORTS + 10):
            record_report(f"/path/{i}/", "GET", report)
        assert len(_report_buffer) == MAX_REPORTS
        # Oldest entries should be evicted
        assert _report_buffer[0]["path"] == "/path/10/"

    def test_record_report_captures_prescriptions(self) -> None:
        """Prescription details should be captured in the record."""
        report = _make_report(num_prescriptions=2, has_critical=True)
        record_report("/test/", "POST", report)
        record = _report_buffer[0]
        assert record["issues"] == 2
        assert record["critical"] is True
        assert len(record["prescriptions"]) == 2

    def test_record_report_captures_timestamp(self) -> None:
        """Records should include a timestamp."""
        report = _make_report()
        record_report("/test/", "GET", report)
        assert "timestamp" in _report_buffer[0]


@pytest.mark.django_db
class TestDashboardView:
    """Tests for the QueryDoctorDashboardView."""

    def setup_method(self) -> None:
        """Clear the report buffer before each test."""
        _report_buffer.clear()

    def test_dashboard_returns_200_for_staff(self) -> None:
        """Staff user should get 200 response."""
        from django.contrib.auth.models import User

        user = User.objects.create_superuser("admin", "admin@test.com", "pass")
        factory = RequestFactory()
        request = factory.get("/admin/query-doctor/dashboard/")
        request.user = user

        view = QueryDoctorDashboardView.as_view()
        response = view(request)
        assert response.status_code == 200

    def test_dashboard_redirects_anonymous(self) -> None:
        """Anonymous user should be redirected."""
        from django.contrib.auth.models import AnonymousUser

        factory = RequestFactory()
        request = factory.get("/admin/query-doctor/dashboard/")
        request.user = AnonymousUser()

        view = QueryDoctorDashboardView.as_view()
        response = view(request)
        assert response.status_code == 302

    def test_dashboard_shows_recorded_reports(self) -> None:
        """Dashboard should include recorded reports in context."""
        from django.contrib.auth.models import User

        report = _make_report(num_prescriptions=3)
        record_report("/api/test/", "GET", report)

        user = User.objects.create_superuser("admin2", "admin2@test.com", "pass")
        factory = RequestFactory()
        request = factory.get("/admin/query-doctor/dashboard/")
        request.user = user

        view = QueryDoctorDashboardView()
        view.request = request
        view.kwargs = {}
        ctx = view.get_context_data()
        assert ctx["total_reports"] == 1
        assert ctx["total_issues"] == 3

    def test_empty_state_renders(self) -> None:
        """Empty buffer should still return valid context."""
        from django.contrib.auth.models import User

        user = User.objects.create_superuser("admin3", "admin3@test.com", "pass")
        factory = RequestFactory()
        request = factory.get("/admin/query-doctor/dashboard/")
        request.user = user

        view = QueryDoctorDashboardView()
        view.request = request
        view.kwargs = {}
        ctx = view.get_context_data()
        assert ctx["total_reports"] == 0
        assert ctx["total_issues"] == 0
        assert ctx["reports"] == []
