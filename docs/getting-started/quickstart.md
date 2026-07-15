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
============================================================
Query Doctor Report
Total queries: 53 | Time: 127.3ms | Issues: 3
============================================================

CRITICAL: N+1 detected: 47 queries for table "myapp_author" (field: author)
   Location: myapp/views.py:83 in get_queryset
   Fix: Add .select_related('author') to your queryset
   Queries: 47 | Est. savings: ~89.0ms

WARNING: Duplicate query: 6 identical queries for table "myapp_book"
   Location: myapp/views.py:91 in get_context_data
   Fix: Assign the queryset result to a variable and reuse it instead of executing the same query multiple times
   Queries: 6 | Est. savings: ~4.2ms

INFO: Missing index: column "published_date" on Book (table "myapp_book") is used in WHERE/ORDER BY but has no index
   Location: myapp/views.py:83 in get_queryset
   Fix: Add to Book's Meta.indexes: indexes = [models.Index(fields=["published_date"], name="idx_myapp_book_published_date")]
```

(With [Rich](https://github.com/Textualize/rich) installed, the same content renders with colors and panels.)

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
- [Management Commands](../guides/management-commands.md) — Full reference for all 6 commands
- [Pytest Plugin](../guides/pytest-plugin.md) — Catch query issues in your test suite
