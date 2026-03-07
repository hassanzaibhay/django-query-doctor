# django-query-doctor

Automated diagnosis and prescriptions for slow Django ORM queries.

Other tools show you *what* queries ran. Query Doctor tells you *how to fix them*.

## Features

- **N+1 Detection** - Finds missing `select_related()` and `prefetch_related()` calls
- **Duplicate Detection** - Flags identical queries that could be cached in a variable
- **Actionable Prescriptions** - Every issue includes the exact code fix, not just a warning
- **Zero Config** - Works by adding one middleware line. All settings have sensible defaults
- **Never Crashes Your App** - All analysis is wrapped in try/except. If we error, your app keeps running
- **No DEBUG Required** - Uses `connection.execute_wrapper()`, works in any environment

## Installation

```bash
pip install django-query-doctor
```

## Quick Start

### 1. Add the middleware

```python
# settings.py
MIDDLEWARE = [
    # ... your other middleware ...
    "query_doctor.QueryDoctorMiddleware",
]
```

That's it. Query Doctor will analyze every request and print prescriptions to stderr when issues are found.

### 2. Or use the context manager for targeted diagnosis

```python
from query_doctor import diagnose_queries

with diagnose_queries() as report:
    books = Book.objects.all()
    for book in books:
        print(book.author.name)  # N+1!

print(f"Issues found: {report.issues}")
for rx in report.prescriptions:
    print(f"  {rx.severity.value}: {rx.description}")
    print(f"  Fix: {rx.fix_suggestion}")
```

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

## Configuration

All settings are optional. Add to `settings.py`:

```python
QUERY_DOCTOR = {
    "ENABLED": True,              # Toggle on/off
    "SAMPLE_RATE": 1.0,           # Fraction of requests to analyze (0.0-1.0)
    "CAPTURE_STACK_TRACES": True,  # Include file:line in prescriptions
    "ANALYZERS": {
        "nplusone": {"enabled": True, "threshold": 3},
        "duplicate": {"enabled": True, "threshold": 2},
    },
    "REPORTERS": ["console"],
    "IGNORE_URLS": ["/admin/", "/health/"],
}
```

## Comparison

| Feature | django-query-doctor | django-debug-toolbar | django-silk |
|---------|:-------------------:|:-------------------:|:-----------:|
| N+1 detection | Yes | No | No |
| Fix suggestions | Yes | No | No |
| Works without DEBUG | Yes | No | Yes |
| Zero config | Yes | No | No |
| CI-friendly | Yes | No | Yes |
| No browser needed | Yes | No | Yes |

## Requirements

- Python >= 3.10
- Django >= 4.2

## License

MIT
