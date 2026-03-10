# django-query-doctor

[![PyPI version](https://img.shields.io/pypi/v/django-query-doctor.svg)](https://pypi.org/project/django-query-doctor/)
[![Python versions](https://img.shields.io/pypi/pyversions/django-query-doctor.svg)](https://pypi.org/project/django-query-doctor/)
[![Django versions](https://img.shields.io/badge/django-4.2%20%7C%205.0%20%7C%205.1%20%7C%205.2-blue.svg)](https://pypi.org/project/django-query-doctor/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/hassanzaibhay/django-query-doctor/actions/workflows/ci.yml/badge.svg)](https://github.com/hassanzaibhay/django-query-doctor/actions)

Automated diagnosis and prescriptions for slow Django ORM queries.

## The Problem

Django's ORM makes it easy to write code that generates hundreds of unnecessary database queries. The most common culprit is the N+1 pattern: iterating over a queryset and accessing a related field triggers a separate query for each row. Tools like django-debug-toolbar can show you *what* queries ran, but they leave you to figure out the fix yourself.

**Query Doctor prescribes the fix.** It tells you exactly which `select_related()` or `prefetch_related()` call to add and where.

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

```
============================================================
Query Doctor Report
Total queries: 53 | Time: 127.3ms | Issues: 2
============================================================

CRITICAL: N+1 detected: 47 queries for table "testapp_author" (field: author)
   Location: myapp/views.py:83 in get_queryset
   Fix: Add .select_related('author') to your queryset
   Queries: 47 | Est. savings: ~89.0ms

WARNING: Duplicate query: 6 identical queries for table "testapp_publisher"
   Location: myapp/views.py:91 in get_context_data
   Fix: Assign the queryset result to a variable and reuse it
   Queries: 6 | Est. savings: ~4.2ms
```

## What It Detects

| Issue Type | What It Finds | Example Fix |
|------------|--------------|-------------|
| **N+1 Queries** | Looping over a queryset and hitting a FK/M2M on each row | `Book.objects.select_related('author')` |
| **Duplicate Queries** | The exact same SQL executed multiple times | Assign the result to a variable and reuse it |

## Usage in Tests

Use the context manager to assert query behavior in pytest:

```python
from query_doctor import diagnose_queries, QueryBudgetError

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

## Configuration

All settings are optional. Add to `settings.py`:

```python
QUERY_DOCTOR = {
    "ENABLED": True,                # Toggle on/off
    "SAMPLE_RATE": 1.0,             # Fraction of requests to analyze (0.0-1.0)
    "CAPTURE_STACK_TRACES": True,   # Include file:line in prescriptions
    "STACK_TRACE_EXCLUDE": [],      # Additional modules to exclude from traces
    "ANALYZERS": {
        "nplusone": {"enabled": True, "threshold": 3},   # Min queries to flag N+1
        "duplicate": {"enabled": True, "threshold": 2},  # Min count to flag duplicates
    },
    "REPORTERS": ["console"],       # Output destinations
    "IGNORE_URLS": ["/admin/", "/health/"],  # Skip these URL prefixes
    "QUERY_BUDGET": {
        "DEFAULT_MAX_QUERIES": None,   # Global default for @query_budget
        "DEFAULT_MAX_TIME_MS": None,   # Global default for @query_budget
    },
}
```

## Compared To

| Feature | query-doctor | debug-toolbar | django-silk | nplusone | auto-prefetch |
|---------|:---:|:---:|:---:|:---:|:---:|
| N+1 detection | Yes | No | No | Yes | N/A |
| Exact fix suggestions | Yes | No | No | No | No |
| Duplicate detection | Yes | No | Yes | No | No |
| Works without DEBUG | Yes | No | Yes | Yes | Yes |
| Zero config | Yes | No | No | Yes | Yes |
| Context manager API | Yes | No | No | No | No |
| Query budget decorator | Yes | No | No | No | No |
| CI-friendly output | Yes | No | Yes | Yes | N/A |
| No browser needed | Yes | No | No | Yes | Yes |
| Auto-fixes queries | No | No | No | No | Yes |

## CI/CD Integration

Management commands for CI pipelines are planned for v0.2. In the meantime, use the `@query_budget` decorator or `diagnose_queries()` context manager in your test suite to fail builds that exceed query limits.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

## Requirements

- Python >= 3.10
- Django >= 4.2

## License

MIT
