#!/usr/bin/env python
"""
Example 14: Admin Dashboard Setup
"""

print("=" * 60)
print("Example 14: Admin Dashboard")
print("=" * 60)

print("""
# Step 1: Enable in settings
QUERY_DOCTOR = {
    "ADMIN_DASHBOARD": {
        "enabled": True,
        "max_reports": 50,  # Ring buffer size
    },
}

# Step 2: Add URL
# urls.py
from django.urls import include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("admin/query-doctor/", include("query_doctor.urls")),
]

# Step 3: Visit /admin/query-doctor/dashboard/
# (Requires staff login — is_staff=True)

# The dashboard shows:
#   - Summary cards: total requests, total issues, critical count
#   - Table of recent requests with query count, time, issues
#   - Expandable detail for each request showing prescriptions
#   - Latest project diagnosis report (if diagnose_project was run)
#   - Auto-refresh toggle
#
# Data is stored in an in-memory ring buffer — no database tables needed.
# When the server restarts, the history is cleared.
""")
