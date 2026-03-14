"""Django admin dashboard for query diagnosis reports.

Provides a lightweight staff-only view showing recent query diagnosis
reports stored in an in-memory ring buffer. No database required.
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime
from typing import Any

from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

from query_doctor.types import DiagnosisReport

logger = logging.getLogger("query_doctor")

MAX_REPORTS = 50

_report_buffer: deque[dict[str, Any]] = deque(maxlen=MAX_REPORTS)
_latest_project_report: dict[str, Any] | None = None


def record_report(request_path: str, method: str, report: DiagnosisReport) -> None:
    """Record a diagnosis report in the ring buffer.

    Called by middleware after each diagnosis when the admin dashboard
    is enabled. Automatically evicts oldest entries when buffer is full.

    Args:
        request_path: The URL path of the request.
        method: The HTTP method (GET, POST, etc.).
        report: The completed diagnosis report.
    """
    _report_buffer.append(
        {
            "timestamp": datetime.now().isoformat(),
            "path": request_path,
            "method": method,
            "total_queries": report.total_queries,
            "total_time_ms": report.total_time_ms,
            "issues": len(report.prescriptions),
            "critical": report.has_critical,
            "prescriptions": [
                {
                    "type": rx.issue_type.value,
                    "severity": rx.severity.value,
                    "description": rx.description,
                    "fix": rx.fix_suggestion,
                    "callsite": (
                        f"{rx.callsite.filepath}:{rx.callsite.line_number}"
                        if rx.callsite
                        else None
                    ),
                }
                for rx in report.prescriptions
            ],
        }
    )
    # deque with maxlen auto-evicts oldest entries


def record_project_report(result: Any) -> None:
    """Store latest project diagnosis for admin dashboard.

    Args:
        result: A ProjectDiagnosisResult from the diagnose_project command.
    """
    global _latest_project_report
    _latest_project_report = {
        "generated_at": result.finished_at,
        "total_urls": result.total_urls_analyzed,
        "total_queries": result.total_queries,
        "total_issues": result.total_issues,
        "health_score": result.overall_health_score,
        "apps": [
            {
                "name": app.app_name,
                "health_score": app.health_score,
                "total_queries": app.total_queries,
                "total_issues": app.total_issues,
                "critical_count": app.critical_count,
            }
            for app in result.app_results
        ],
    }


def _is_staff(user: Any) -> bool:
    """Check if user is active staff member."""
    return bool(user.is_active and user.is_staff)


@method_decorator([login_required, user_passes_test(_is_staff)], name="dispatch")
class QueryDoctorDashboardView(TemplateView):
    """Staff-only dashboard showing recent query diagnosis reports.

    Displays summary statistics and a table of recent requests
    with expandable prescription details.
    """

    template_name = "query_doctor/dashboard.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Build template context with report data.

        Returns:
            Context dict with reports, totals, and statistics.
        """
        ctx = super().get_context_data(**kwargs)
        ctx["reports"] = list(reversed(_report_buffer))
        ctx["total_reports"] = len(_report_buffer)
        ctx["total_issues"] = sum(r["issues"] for r in _report_buffer)
        ctx["critical_count"] = sum(1 for r in _report_buffer if r["critical"])
        ctx["project_report"] = _latest_project_report
        return ctx
