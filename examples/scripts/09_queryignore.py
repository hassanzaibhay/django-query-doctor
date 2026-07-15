#!/usr/bin/env python
"""
Example 9: .queryignore File
"""

print("=" * 60)
print("Example 9: .queryignore File")
print("=" * 60)

print("""
# Create a .queryignore file in your project root (same level as manage.py):

# .queryignore
# ============

# Ignore findings mentioning Django internal tables
# (sql rules match the finding DESCRIPTION, which contains table names)
sql:%django_session%
sql:%django_content_type%

# Ignore findings from migration modules
# (file rules glob against the FULL path — start with *)
file:*migrations*

# Ignore a specific known-acceptable callsite
# (must equal the path exactly as printed in the report)
callsite:/app/myapp/views.py:142

# Ignore N+1 in a legacy view we can't refactor yet
# (issue types are enum values: n_plus_one, duplicate_query, ...)
ignore:n_plus_one:myapp/views.py:LegacyReportView

# Ignore all findings from management commands
file:*myapp/management/commands/*

# Lines starting with # are comments
# Blank lines are ignored

# The file location is not configurable — query-doctor looks for
# .queryignore next to manage.py (or the current working directory).
# Rules apply in the middleware and fix_queries.
""")
