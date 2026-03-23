# django-query-doctor

Diagnose and fix slow Django ORM queries. Detects N+1s, duplicates, missing indexes, and more — with exact file:line references and actionable fixes.

[![PyPI](https://img.shields.io/pypi/v/django-query-doctor.svg)](https://pypi.org/project/django-query-doctor/)
[![Tests](https://img.shields.io/github/actions/workflow/status/hassanzaibhay/django-query-doctor/ci.yml)](https://github.com/hassanzaibhay/django-query-doctor/actions)
[![Python](https://img.shields.io/pypi/pyversions/django-query-doctor.svg)](https://pypi.org/project/django-query-doctor/)
[![Django](https://img.shields.io/badge/django-4.2%20|%205.0%20|%205.1%20|%205.2%20|%206.0-blue)](https://pypi.org/project/django-query-doctor/)
[![License](https://img.shields.io/pypi/l/django-query-doctor.svg)](https://opensource.org/licenses/MIT)

## The Problem

Every Django app accumulates hidden query inefficiencies — N+1 loops behind serializers, duplicate fetches scattered across views, full table scans on unindexed columns. django-query-doctor intercepts queries at runtime using `connection.execute_wrapper()`, runs them through 8 analyzers, and produces prescriptions with the exact file, line, and code fix. It works in middleware, tests, CI pipelines, and management commands — no `DEBUG=True` required.

## Install

```bash
pip install django-query-doctor
```

```python
# settings.py
INSTALLED_APPS = [..., "query_doctor"]
MIDDLEWARE = [..., "query_doctor.middleware.QueryDoctorMiddleware"]
```

## See It in Action

```python
from query_doctor.context_managers import diagnose_queries

with diagnose_queries() as report:
    books = list(Book.objects.all())
    for book in books:
        _ = book.author.name  # triggers N+1

assert report.issues > 0
print(f"Found {report.issues} issues in {report.total_queries} queries")
```

Output:

```
[CRITICAL] N+1 Query
  50 queries fetching Author for each Book.
  Location: views.py:42
  Fix: Add select_related('author') to queryset
```

## What It Detects

| Issue | What It Catches |
|-------|-----------------|
| N+1 Queries | Related objects loaded one-per-row in loops |
| Duplicate Queries | Same SQL executed multiple times per request |
| Missing Indexes | Filters on columns without database indexes |
| Fat SELECT | Fetching all columns when only a few are used |
| QuerySet Evaluation | `len(qs)` instead of `qs.count()`, `bool(qs)` instead of `qs.exists()` |
| DRF Serializer | N+1 from nested serializers or missing `select_related` |
| Query Complexity | Excessive JOINs, subqueries, or OR chains |
| SerializerMethodField | AST analysis of `get_<field>` method bodies for hidden N+1s |

Every prescription includes: severity, file:line, and the exact code fix.

## QueryTurbo (v2.0)

QueryTurbo reduces SQL compilation overhead by caching compiled query structures and extracting parameters directly from Django's Query tree, bypassing repeated calls to `SQLCompiler.as_sql()`. Queries are validated across 3 executions before the compilation step is skipped entirely. Enable it in settings:

```python
QUERY_DOCTOR = {
    "TURBO": {"ENABLED": True}
}
```

[Full QueryTurbo guide →](https://hassanzaibhay.github.io/django-query-doctor/guides/queryturbo/)

## Requirements

- Python 3.10+
- Django 4.2, 5.0, 5.1, 5.2, or 6.0
- Optional: Rich (styled console), DRF (serializer analysis), psycopg3 (prepared statements)

## Links

[📖 Documentation](https://hassanzaibhay.github.io/django-query-doctor/)  |  [📦 PyPI](https://pypi.org/project/django-query-doctor/)  |  [📝 Changelog](https://hassanzaibhay.github.io/django-query-doctor/changelog/)  |  [🐛 Issues](https://github.com/hassanzaibhay/django-query-doctor/issues)

## License

MIT
