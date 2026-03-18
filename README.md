# django-query-doctor

[![PyPI version](https://img.shields.io/pypi/v/django-query-doctor.svg)](https://pypi.org/project/django-query-doctor/)
[![Python versions](https://img.shields.io/pypi/pyversions/django-query-doctor.svg)](https://pypi.org/project/django-query-doctor/)
[![Django versions](https://img.shields.io/badge/django-4.2%20%7C%205.0%20%7C%205.1%20%7C%205.2%20%7C%206.0-blue.svg)](https://pypi.org/project/django-query-doctor/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/hassanzaibhay/django-query-doctor/actions/workflows/ci.yml/badge.svg)](https://github.com/hassanzaibhay/django-query-doctor/actions)

Automated diagnosis and prescriptions for slow Django ORM queries.

## The Problem

Django's ORM makes it easy to write code that generates hundreds of unnecessary database queries. The most common culprit is the **N+1 pattern**: iterating over a queryset and accessing a related field triggers a separate query for each row. Other silent performance killers include duplicate queries, missing database indexes, and unoptimized DRF serializers.

Tools like django-debug-toolbar can show you *what* queries ran, but they leave you to figure out the fix yourself.

## The Solution

**Query Doctor doesn't just detect problems — it prescribes the fix.** For every issue found, you get:

- The exact issue type and severity
- The file, line number, and function where it originated
- A concrete code fix you can copy-paste

<p align="center">
  <img src="https://raw.githubusercontent.com/hassanzaibhay/django-query-doctor/main/examples/screenshots/quick_start.svg" alt="Quick Start" width="720">
</p>

## Quick Start

**Step 1:** Install the package

```bash
pip install django-query-doctor
```

**Step 2:** Add the middleware

```python
# settings.py
MIDDLEWARE = [
    # ... your other middleware ...
    "query_doctor.QueryDoctorMiddleware",
]
```

**Step 3:** Run your app and check stderr for prescriptions.

That's it. Zero config required.

## Example Output

```text
============================================================
Query Doctor Report
Total queries: 53 | Time: 127.3ms | Issues: 3
============================================================

CRITICAL: N+1 detected: 47 queries for table "myapp_author" (field: author)
   Location: myapp/views.py:83 in get_queryset
   Code: books = Book.objects.all()
   Fix: Add .select_related('author') to your queryset
   Queries: 47 | Est. savings: ~89.0ms

WARNING: Duplicate query: 6 identical queries for table "myapp_publisher"
   Location: myapp/views.py:91 in get_context_data
   Fix: Assign the queryset result to a variable and reuse it
   Queries: 6 | Est. savings: ~4.2ms

INFO: Column "published_date" in WHERE clause has no index on table "myapp_book"
   Fix: Add models.Index(fields=["published_date"]) to Book's Meta.indexes
```

<p align="center">
  <img src="https://raw.githubusercontent.com/hassanzaibhay/django-query-doctor/main/examples/screenshots/console_output.svg" alt="Console Output" width="820">
</p>

## What It Detects

| Issue Type | Severity | What It Finds | Example Fix |
|------------|----------|---------------|-------------|
| **N+1 Queries** | CRITICAL | Looping over a queryset and hitting a FK/M2M on each row | `Book.objects.select_related('author')` |
| **Duplicate Queries** | WARNING | The exact same SQL executed multiple times | Assign the result to a variable and reuse it |
| **Missing Indexes** | INFO | WHERE/ORDER BY columns without a database index | `Meta.indexes = [models.Index(fields=["field"])]` |
| **DRF Serializer N+1** | WARNING | Nested serializers without prefetching | `select_related()` / `prefetch_related()` on the view queryset |
| **Fat SELECT** | INFO | `SELECT *` when only a few columns are used | `.only('field1', 'field2')` or `.values('field1', 'field2')` |
| **QuerySet Evaluation** | WARNING | Full queryset evaluation patterns (e.g., `list()` on large tables) | `.iterator()`, `.exists()`, `.count()`, or slicing |
| **Query Complexity** | WARNING/CRITICAL | Queries with excessive JOINs, subqueries, OR chains, GROUP BY | Break into simpler queries, use `.select_related()` for 1-2 FKs and `.prefetch_related()` for the rest |

## Usage in Tests

Use the context manager to assert query behavior in pytest:

```python
from query_doctor import diagnose_queries

def test_book_list_no_nplusone():
    with diagnose_queries() as report:
        books = list(Book.objects.select_related("author").all())
        for book in books:
            _ = book.author.name

    assert report.issues == 0

def test_book_list_query_count():
    with diagnose_queries() as report:
        list(Book.objects.all())

    assert report.total_queries <= 5
```

Or use the `@query_budget` decorator to enforce limits:

```python
from query_doctor import query_budget

@query_budget(max_queries=10, max_time_ms=100)
def my_view(request):
    return render(request, "books.html", {"books": Book.objects.all()})
```

<p align="center">
  <img src="https://raw.githubusercontent.com/hassanzaibhay/django-query-doctor/main/examples/screenshots/query_budget.svg" alt="Query Budget" width="820">
</p>

## Management Commands

### `check_queries` — Analyze a URL for query issues

```bash
# Console output (default)
python manage.py check_queries --url /api/books/

# JSON output for CI parsing
python manage.py check_queries --url /api/books/ --format json

# Fail CI if critical issues found
python manage.py check_queries --url /api/books/ --fail-on critical
```

### `query_budget` — Enforce query count limits

```bash
# Check that a code block stays within budget
python manage.py query_budget --max-queries 20 \
    --execute "from myapp.models import Book; list(Book.objects.select_related('author').all())"

# Also enforce time budget
python manage.py query_budget --max-queries 20 --max-time-ms 100 \
    --execute "from myapp.models import Book; list(Book.objects.all())"
```

### `fix_queries` — Auto-apply diagnosed fixes

```bash
# Preview fixes (dry-run, default)
python manage.py fix_queries --url /api/books/

# Apply fixes with backups
python manage.py fix_queries --url /api/books/ --apply

# Filter by issue type
python manage.py fix_queries --url /api/books/ --apply --issue-type nplusone

# Filter by file
python manage.py fix_queries --url /api/books/ --apply --file myapp/views.py
```

### `diagnose_project` — Full project health scan

```bash
# Scan entire project, generate HTML report
python manage.py diagnose_project

# Output to specific file
python manage.py diagnose_project --output health_report.html

# Only scan specific apps
python manage.py diagnose_project --apps myapp accounts

# JSON output for CI
python manage.py diagnose_project --format json

# Exclude URL patterns
python manage.py diagnose_project --exclude-urls /admin/ /health/
```

Generates a standalone HTML report with:
- Per-app health scores (0-100)
- Sortable app scoreboard
- Per-URL query breakdown with prescriptions
- Executive summary with critical issue highlights

Run before each release to catch query regressions across your entire project.

<p align="center">
  <img src="https://raw.githubusercontent.com/hassanzaibhay/django-query-doctor/main/examples/screenshots/project_diagnosis.svg" alt="Project Health Scan" width="820">
</p>

## Celery Task Support

Diagnose queries inside Celery tasks (or any callable) with `@diagnose_task`:

```python
from celery import shared_task
from query_doctor.celery_integration import diagnose_task

@shared_task
@diagnose_task
def send_weekly_report():
    users = User.objects.all()
    for user in users:
        user.profile.email  # N+1 detected and reported

# With a callback:
@shared_task
@diagnose_task(on_report=lambda r: logger.info(f"Issues: {len(r.prescriptions)}"))
def process_orders():
    ...
```

Celery is **not** a required dependency. If not installed, the decorator works as a plain wrapper.

## Async View Support

The middleware is fully async-compatible. It automatically detects whether your Django app uses async views and routes accordingly:

```python
# settings.py — same middleware, no extra config needed
MIDDLEWARE = [
    "query_doctor.QueryDoctorMiddleware",
]

# Works with both sync and async views
async def my_async_view(request):
    books = await sync_to_async(list)(Book.objects.select_related("author").all())
    return JsonResponse({"count": len(books)})
```

## Custom Analyzer Plugins

Third-party packages can register custom analyzers via Python entry points:

```toml
# In your package's pyproject.toml
[project.entry-points."query_doctor.analyzers"]
my_analyzer = "my_package.analyzers:MyCustomAnalyzer"
```

```python
from query_doctor.analyzers.base import BaseAnalyzer, Prescription

class MyCustomAnalyzer(BaseAnalyzer):
    name = "my_analyzer"

    def analyze(self, queries):
        prescriptions = []
        # Your detection logic here
        return prescriptions
```

Use `discover_analyzers()` to load all built-in and third-party analyzers:

```python
from query_doctor.plugin_api import discover_analyzers

analyzers = discover_analyzers()  # Built-in + registered plugins
```

## OpenTelemetry Export

Send diagnosis results as OpenTelemetry spans and events:

```python
QUERY_DOCTOR = {
    "REPORTERS": ["console", "otel"],
}
```

Each request creates a span with query count, timing, and issue attributes. Individual prescriptions are added as span events. Requires `opentelemetry-api` and `opentelemetry-sdk` (optional dependencies).

```bash
pip install django-query-doctor[otel]
```

## Auto-Fix Mode

Query Doctor can automatically apply fixes to your source code:

```bash
# Preview fixes as a diff (default — safe, changes nothing)
python manage.py fix_queries --url /api/books/

# Apply fixes to source files (creates .bak backups)
python manage.py fix_queries --url /api/books/ --apply

# Only fix specific issue types
python manage.py fix_queries --url /api/books/ --apply --issue-type nplusone fat_select

# Only fix specific files
python manage.py fix_queries --url /api/books/ --apply --file myapp/views.py

# Skip backups (not recommended)
python manage.py fix_queries --url /api/books/ --apply --no-backup
```

By default, `fix_queries` runs in **dry-run mode** — it shows you the proposed diff without modifying any files. Pass `--apply` to write changes. Backup files (`.bak`) are created automatically.

**Safety guarantees:**
- Dry-run is the default — you must explicitly opt in to changes
- Backup files created before any modification
- Never modifies files outside your Django project directory
- Skips ambiguous fixes with a warning rather than guessing

<p align="center">
  <img src="https://raw.githubusercontent.com/hassanzaibhay/django-query-doctor/main/examples/screenshots/auto_fix.svg" alt="Auto-Fix Preview" width="820">
</p>

## Admin Dashboard

A built-in dashboard for viewing recent query diagnosis reports:

```python
# settings.py — enable the dashboard
QUERY_DOCTOR = {
    "ADMIN_DASHBOARD": {
        "enabled": True,
        "max_reports": 50,
    },
}
```

```python
# urls.py — add the dashboard URL
from django.urls import include

urlpatterns = [
    path("admin/query-doctor/", include("query_doctor.urls")),
    # ...
]
```

The dashboard shows recent requests with query counts, timing, and prescriptions. It requires Django staff access (`is_staff=True`) and stores reports in an in-memory ring buffer — no database tables or migrations required.

## .queryignore

Suppress known false positives with a `.queryignore` file in your project root:

```text
# .queryignore — Patterns to exclude from analysis

# Ignore queries matching SQL patterns
sql:SELECT * FROM django_session%

# Ignore queries originating from specific files
file:myapp/migrations/*
file:myapp/management/commands/seed_data.py

# Ignore specific callsites
callsite:myapp/views.py:142

# Ignore specific issue types for specific paths
ignore:nplusone:myapp/views.py:LegacyReportView
```

Lines starting with `#` are comments. The file is automatically detected at your project root, or set a custom path:

```python
QUERY_DOCTOR = {
    "QUERYIGNORE_PATH": "/path/to/.queryignore",
}
```

## Diff-Aware CI

Only analyze files changed in your branch — ideal for large codebases:

```bash
# Only report issues in files changed vs main
python manage.py check_queries --url /api/books/ --diff=main

# Compare against a specific commit
python manage.py check_queries --url /api/books/ --diff=abc123

# Compare against another branch
python manage.py check_queries --url /api/books/ --diff=origin/develop
```

If `git` is not available or the ref is invalid, all prescriptions are included (safe fallback).

## Pytest Plugin

Use the built-in pytest plugin for query assertions in your test suite:

```python
def test_optimized_view(query_doctor):
    books = list(Book.objects.select_related("author").all())
    for book in books:
        _ = book.author.name

    assert query_doctor.issues == 0
    assert query_doctor.total_queries <= 10
```

The plugin is automatically registered when you install `django-query-doctor`.

<p align="center">
  <img src="https://raw.githubusercontent.com/hassanzaibhay/django-query-doctor/main/examples/screenshots/test_usage.svg" alt="Test Usage" width="820">
</p>

## Configuration

All settings are optional. Add to `settings.py`:

```python
QUERY_DOCTOR = {
    "ENABLED": True,                # Toggle on/off
    "SAMPLE_RATE": 1.0,             # Fraction of requests to analyze (0.0-1.0)
    "CAPTURE_STACK_TRACES": True,   # Include file:line in prescriptions
    "STACK_TRACE_EXCLUDE": [],      # Additional modules to exclude from traces
    "ANALYZERS": {
        "nplusone": {"enabled": True, "threshold": 3},
        "duplicate": {"enabled": True, "threshold": 2},
        "missing_index": {"enabled": True},
        "fat_select": {"enabled": True},
        "queryset_eval": {"enabled": True},
        "drf_serializer": {"enabled": True},
        "complexity": {"enabled": True, "threshold": 8},
    },
    "REPORTERS": ["console"],       # Options: "console", "json", "log", "html", "otel"
    "IGNORE_URLS": ["/admin/", "/health/"],
    "QUERY_BUDGET": {
        "DEFAULT_MAX_QUERIES": None,
        "DEFAULT_MAX_TIME_MS": None,
    },
    "ADMIN_DASHBOARD": {
        "enabled": False,           # Must be explicitly enabled
        "max_reports": 50,          # Ring buffer size
    },
    "QUERYIGNORE_PATH": None,       # Custom .queryignore path (default: project root)
}
```

## Compared To

| Feature | query-doctor | debug-toolbar | django-silk | nplusone | auto-prefetch |
|---------|:---:|:---:|:---:|:---:|:---:|
| N+1 detection | Yes | No | No | Yes | N/A |
| Exact fix suggestions | Yes | No | No | No | No |
| Duplicate detection | Yes | No | Yes | No | No |
| Missing index detection | Yes | No | No | No | No |
| DRF serializer analysis | Yes | No | No | No | No |
| Works without DEBUG | Yes | No | Yes | Yes | Yes |
| Zero config | Yes | No | No | Yes | Yes |
| Context manager API | Yes | No | No | No | No |
| Query budget decorator | Yes | No | No | No | No |
| Management commands | Yes | No | Yes | No | No |
| JSON / log reporters | Yes | No | Yes | No | No |
| Pytest plugin | Yes | No | No | No | No |
| Celery task support | Yes | No | No | No | No |
| Async view support | Yes | No | No | No | No |
| Custom analyzer plugins | Yes | No | No | No | No |
| OpenTelemetry export | Yes | No | No | No | No |
| No browser needed | Yes | No | No | Yes | Yes |
| Query complexity scoring | Yes | No | No | No | No |
| .queryignore file | Yes | No | No | No | No |
| Diff-aware CI mode | Yes | No | No | No | No |
| Admin dashboard | Yes | Yes | Yes | No | No |
| Full project health scan | Yes | No | No | No | No |
| Auto-fixes queries | Yes | No | No | No | Yes |

## Requirements

- Python >= 3.10
- Django >= 4.2 (tested up to 6.0)
- Rich >= 13.0 *(optional, for styled console output)*
- Celery >= 5.0 *(optional, for task diagnosis)*
- opentelemetry-api >= 1.0 *(optional, for OTel export)*

Install optional extras:

```bash
pip install django-query-doctor[rich]       # Rich console output
pip install django-query-doctor[otel]       # OpenTelemetry export
pip install django-query-doctor[all]        # Everything
```

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

```bash
git clone https://github.com/hassanzaibhay/django-query-doctor.git
cd django-query-doctor
pip install -e ".[dev]"
pytest
```

## License

MIT
