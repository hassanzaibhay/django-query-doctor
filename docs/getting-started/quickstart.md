# Quick Start

Get django-query-doctor analyzing your queries in under 2 minutes.

## Step 1: Install
```bash
pip install django-query-doctor
```

## Step 2: Configure
```python title="settings.py"
INSTALLED_APPS = [
    ...,
    "query_doctor",
]

MIDDLEWARE = [
    ...,
    "query_doctor.middleware.QueryDoctorMiddleware",
]
```

## Step 3: Run Your Server
```bash
python manage.py runserver
```

Browse your app as normal. Every request will now show query analysis in your console:

```
══════════════════════════════════════════════════════
 Query Doctor Report
 Total queries: 53 | Time: 127.3ms | Issues: 3
══════════════════════════════════════════════════════

 CRITICAL  N+1 detected: 47 queries for table "myapp_author"
   Location: myapp/views.py:83 in get_queryset
   Fix: Add .select_related('author') to your queryset
   Queries: 47 | Est. savings: ~89.0ms

 WARNING  Duplicate query: 6 identical queries
   Location: myapp/views.py:91 in get_context_data
   Fix: Assign the queryset result to a variable and reuse it

 INFO  Column "published_date" has no index on "myapp_book"
   Fix: Add models.Index(fields=["published_date"]) to Book's Meta.indexes
```

Every issue includes the exact file, line number, and a ready-to-apply fix.

## Alternative: Use Without Middleware

If you prefer not to run analysis on every request, skip the middleware and use management commands instead:
```bash
# Analyze specific URL patterns
python manage.py check_queries --url /api/books/

# Full project health scan
python manage.py diagnose_project

# Auto-apply suggested fixes (dry-run by default)
python manage.py fix_queries --url /api/books/
```

!!! note
    Management commands run analysis via your URL patterns without the middleware. This is the recommended approach for large codebases — keep middleware off day-to-day, run commands in CI or on-demand.

## What's Next?

- [Configuration](configuration.md) — Customize which analyzers run, set thresholds, choose reporters
- [Analyzers Overview](../analyzers/overview.md) — Deep dive into what each analyzer detects
- [Management Commands](../guides/management-commands.md) — Full reference for all 4 commands
- [Pytest Plugin](../guides/pytest-plugin.md) — Catch query issues in your test suite
