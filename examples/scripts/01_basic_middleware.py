#!/usr/bin/env python
"""
Example 1: Basic Middleware Setup

The simplest way to use query-doctor. Just add the middleware
and every request gets diagnosed automatically.
"""

# settings.py — just add one line:
SETTINGS_EXAMPLE = """
MIDDLEWARE = [
    # ... your other middleware ...
    "query_doctor.QueryDoctorMiddleware",  # <-- Add this
]

# That's it! Zero config. Run your app and check stderr.
"""

# What you'll see in the console:
EXPECTED_OUTPUT = """
============================================================
Query Doctor Report
Total queries: 28 | Time: 45.2ms | Issues: 2
============================================================

CRITICAL: N+1 detected: 25 queries for table "myapp_author"
   Location: myapp/views.py:15 in get_queryset
   Fix: Add .select_related('author') to your queryset

WARNING: Duplicate query executed 3 times
   Location: myapp/views.py:22 in get_context_data
   Fix: Assign the queryset result to a variable and reuse it
"""

print("=" * 60)
print("Example 1: Basic Middleware Setup")
print("=" * 60)
print(SETTINGS_EXAMPLE)
print("Expected console output:")
print(EXPECTED_OUTPUT)
