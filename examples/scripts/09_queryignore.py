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

# Ignore Django internal queries
sql:SELECT * FROM django_session%
sql:SELECT * FROM django_content_type%

# Ignore queries from migrations
file:*/migrations/*

# Ignore a specific known-acceptable callsite
callsite:myapp/views.py:142

# Ignore N+1 in a legacy view we can't refactor yet
ignore:nplusone:myapp/views.py:LegacyReportView

# Ignore all queries from management commands
file:myapp/management/commands/*

# Lines starting with # are comments
# Blank lines are ignored


# Optional: set custom path in settings
QUERY_DOCTOR = {
    "QUERYIGNORE_PATH": "/path/to/custom/.queryignore",
}
""")
