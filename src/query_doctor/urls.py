"""URL configuration for django-query-doctor admin dashboard.

Users opt in by including these URLs in their project's urlconf:

    path("admin/query-doctor/", include("query_doctor.urls"))
"""

from __future__ import annotations

from django.urls import path

from query_doctor.admin_panel import QueryDoctorDashboardView

app_name = "query_doctor"

urlpatterns = [
    path("dashboard/", QueryDoctorDashboardView.as_view(), name="dashboard"),
]
