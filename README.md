# django-query-doctor 🩺

**From diagnosis to prescription to cure.**

The only Django package that diagnoses ORM query problems AND automatically
optimizes the queries that are already correct.

[![PyPI](https://img.shields.io/pypi/v/django-query-doctor.svg)](https://pypi.org/project/django-query-doctor/)
[![Tests](https://img.shields.io/github/actions/workflow/status/hassanzaibhay/django-query-doctor/ci.yml)](https://github.com/hassanzaibhay/django-query-doctor/actions)
[![Python](https://img.shields.io/pypi/pyversions/django-query-doctor.svg)](https://pypi.org/project/django-query-doctor/)
[![Django](https://img.shields.io/badge/django-4.2%20|%205.0%20|%205.1%20|%205.2%20|%206.0-blue)](https://pypi.org/project/django-query-doctor/)
[![License](https://img.shields.io/pypi/l/django-query-doctor.svg)](https://opensource.org/licenses/MIT)

## What's New in v2.0

- **QueryTurbo** — Three-phase SQL compilation cache with trust lifecycle
  (UNTRUSTED -> TRUSTED -> POISONED). On trusted cache hits, skips
  `as_sql()` entirely and extracts params directly from the Query tree.
  Enables automatic prepared statements on PostgreSQL via consistent SQL
  string reuse.
- **Prepared Statement Bridge** — Automatically enables database-level
  prepared statements on PostgreSQL (psycopg3). Skips query planner on
  repeat queries.
- **AST SerializerMethodField Analyzer** — Static analysis of DRF
  `get_<field>` methods. Catches hidden N+1 queries that runtime tools miss.
- **Per-File Analysis** — `--file` and `--module` flags to focus
  diagnosis on specific parts of your codebase.
- **Benchmark Dashboard** — Interactive HTML report with Chart.js
  showing cache hit rates and top optimized queries.
- **GitHub Actions CI Integration** — Inline PR annotations, Markdown
  PR comments, and JSON reports for CI/CD pipelines.
- **Baseline Snapshots** — Save current issues to a baseline file.
  On subsequent runs, detect only new regressions. Fail CI on new issues.
- **Smart Prescription Grouping** — Group related issues by file+analyzer,
  root cause, or view for cleaner output.
- **Async-Safe Context Managers** — `turbo_enabled()` / `turbo_disabled()`
  now use `contextvars.ContextVar` instead of `threading.local()`, making
  them safe for ASGI deployments with concurrent coroutines.

## Quick Start

### Installation

```bash
pip install django-query-doctor
```

### Basic Setup (Diagnosis)

```python
# settings.py
INSTALLED_APPS = [
    ...
    'query_doctor',
]

MIDDLEWARE = [
    ...
    'query_doctor.QueryDoctorMiddleware',
]
```

That's it. Zero config required. Check stderr for prescriptions.

### Enable QueryTurbo (Optimization)

```python
# settings.py
QUERY_DOCTOR = {
    'TURBO': {
        'ENABLED': True,           # Opt-in: caches SQL compilation
        'MAX_SIZE': 1024,          # Max cached query patterns
        'PREPARE_ENABLED': True,   # Prepared statements (PostgreSQL + psycopg3)
        'PREPARE_THRESHOLD': 5,    # Cache hits before preparing
    },
}
```

Zero application code changes. QueryTurbo works transparently with all
Django-supported databases.

## Features

### 🔬 Diagnosis (v1.0+)

| Analyzer | What It Detects |
|---|---|
| N+1 Query | Related objects loaded in loops |
| Duplicate Query | Same SQL executed multiple times per request |
| Missing Index | Frequent filters on non-indexed fields |
| Fat SELECT | Fetching all columns when only a few are needed |
| QuerySet Evaluation | `len()` instead of `.count()`, `bool()` instead of `.exists()` |
| DRF Serializer | N+1 from nested serializers, missing `select_related` |
| Query Complexity | Excessive JOINs, subqueries, OR chains |
| **SerializerMethodField** *(v2.0)* | **AST analysis of `get_<field>` method bodies** |

Every prescription includes: severity, file:line, and the exact code fix.

### 🚀 QueryTurbo — SQL Template Validation Cache (v2.0)

QueryTurbo fingerprints each query's structure and validates that identical
structures produce identical SQL. When your code runs
`User.objects.filter(status='active')` and later
`User.objects.filter(status='inactive')`, the SQL template is identical —
only the parameter differs. QueryTurbo detects this, caches the template,
and validates subsequent compilations against the cache.

**What QueryTurbo provides:**

1. **Prepared Statement Automation** — By ensuring the same SQL string is
   reused for recurring query patterns, psycopg3 automatically prepares
   queries at the protocol level after a configurable number of executions,
   skipping PostgreSQL's query planner on repeat queries.
2. **Collision Detection** — Validates that structurally fingerprinted
   queries produce matching SQL. Detects and evicts mismatches, catching
   edge cases where Django's ORM produces different SQL for similar
   structures.

**Compilation-Skip Benchmarks** (v2.0, trusted cache hits skip `as_sql()` entirely):

| Query Pattern | Speedup | Saved per Query |
|---|---|---|
| Simple filter | 123x | 38.8 μs |
| Multi filter | 153x | 49.2 μs |
| select_related | 294x | 92.5 μs |
| Deep select_related | 374x | 121.1 μs |
| Annotate | 214x | 68.6 μs |
| Complex (JOINs + Q + annotate) | 1,050x | 337.9 μs |

*Measured on SQLite (compilation-only, no DB I/O). Run `python benchmarks/run.py` to reproduce.*

On PostgreSQL with psycopg3, prepared statements provide additional savings
of 0.5–5ms of query planner time per repeat query, with the greatest
benefit on complex queries involving multiple JOINs, annotations, or
subqueries.

**Multi-Database Support:**

| Backend | SQL Cache | Prepared Statements | Notes |
|---|---|---|---|
| PostgreSQL (psycopg3) | ✅ | ✅ Auto via protocol | Best performance |
| PostgreSQL (psycopg2) | ✅ | ❌ | Cache still helps |
| MySQL | ✅ | ❌ | Cache still helps |
| SQLite | ✅ | ❌ | Good for dev/test |
| Oracle | ✅ | ✅ Implicit cursor cache | Via cx_Oracle |

### 📊 Benchmark Dashboard

```bash
python manage.py query_doctor_report --output=report.html
```

Generates a standalone HTML report with:
- Cache hit rate and utilization
- Top optimized queries by hit count
- Prepared statement statistics
- Interactive Chart.js graphs

### 🔍 AST SerializerMethodField Analyzer (v2.0)

Statically analyzes DRF `get_<field>` method bodies using `ast.parse()`.
Detects four N+1 patterns that runtime tools miss:

```python
class MySerializer(serializers.ModelSerializer):
    total = serializers.SerializerMethodField()
    author_name = serializers.SerializerMethodField()

    def get_total(self, obj):
        return obj.items.count()      # N+1: COUNT per object

    def get_author_name(self, obj):
        return obj.author.name        # N+1 if no select_related
```

```bash
python manage.py check_serializers
python manage.py check_serializers --app=myapp
python manage.py check_serializers --file=myapp/serializers.py
```

### 📂 Per-File Analysis

```bash
# Focus on a specific file
python manage.py check_queries --file=myapp/views.py

# Focus on a module
python manage.py check_queries --module=myapp.views

# Combine with other flags
python manage.py check_queries --file=myapp/views.py --fail-on warning
```

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
```

Or use the `@query_budget` decorator to enforce limits:

```python
from query_doctor import query_budget

@query_budget(max_queries=10, max_time_ms=100)
def my_view(request):
    return render(request, "books.html", {"books": Book.objects.all()})
```

## Management Commands

### `check_queries` — Analyze a URL

```bash
python manage.py check_queries --url /api/books/
python manage.py check_queries --url /api/books/ --format json
python manage.py check_queries --url /api/books/ --fail-on critical
python manage.py check_queries --url /api/books/ --diff=main
python manage.py check_queries --save-baseline=.query-baseline.json
python manage.py check_queries --baseline=.query-baseline.json --fail-on-regression
python manage.py check_queries --group=file_analyzer
```

### `check_serializers` — AST analysis of DRF serializers *(v2.0)*

```bash
python manage.py check_serializers
python manage.py check_serializers --app=myapp
python manage.py check_serializers --format=json --fail-on warning
```

### `query_doctor_report` — Benchmark dashboard *(v2.0)*

```bash
python manage.py query_doctor_report
python manage.py query_doctor_report --output=report.html
```

### `diagnose_project` — Full project health scan

```bash
python manage.py diagnose_project
python manage.py diagnose_project --output health_report.html
python manage.py diagnose_project --apps myapp accounts --format json
python manage.py diagnose_project --save-baseline=.project-baseline.json
python manage.py diagnose_project --baseline=.project-baseline.json --fail-on-regression
python manage.py diagnose_project --group=root_cause
```

### `fix_queries` — Auto-apply diagnosed fixes

```bash
python manage.py fix_queries --url /api/books/               # Dry-run (default)
python manage.py fix_queries --url /api/books/ --apply        # Apply with backups
python manage.py fix_queries --url /api/books/ --apply --issue-type nplusone
```

### `query_budget` — Enforce query count limits

```bash
python manage.py query_budget --max-queries 20 \
    --execute "from myapp.models import Book; list(Book.objects.select_related('author').all())"
```

## How QueryTurbo Addresses Django Ticket #20516

Django Ticket #20516 (opened 2013, still open) requested prepared statement
support for the ORM. It was never implemented because it required:

1. A way to identify recurring query patterns
2. A way to separate SQL templates from parameters
3. A bridge to database PREPARE/EXECUTE mechanisms

QueryTurbo provides all three — automatically. Instead of requiring an
explicit `.prepare()` API on QuerySets (as the ticket proposed), QueryTurbo
makes it transparent: cache the SQL template, reuse it, and let psycopg3's
automatic preparation kick in after the threshold.

## Comparison

| Feature | debug-toolbar | silk | nplusone | auto-prefetch | **query-doctor v2** |
|---|---|---|---|---|---|
| N+1 detection | ✓ (manual) | ✓ (manual) | ✓ | — | **✓ (automatic)** |
| Duplicate detection | — | — | — | — | **✓** |
| DRF-aware analysis | — | — | — | — | **✓** |
| SerializerMethodField AST | — | — | — | — | **✓** |
| SQL compilation caching | — | — | — | — | **✓** |
| Prepared statements | — | — | — | — | **✓** |
| Per-file filtering | — | — | — | — | **✓** |
| CI/pytest integration | — | — | — | — | **✓** |
| Benchmark dashboard | — | ✓ | — | — | **✓** |
| Production-safe | ✗ | ✗ | ✓ | ✓ | **✓** |

## Configuration Reference

```python
QUERY_DOCTOR = {
    # --- Diagnosis ---
    'ENABLED': True,
    'SAMPLE_RATE': 1.0,
    'CAPTURE_STACK_TRACES': True,
    'ANALYZERS': {
        'nplusone': {'enabled': True, 'threshold': 3},
        'duplicate': {'enabled': True, 'threshold': 2},
        'missing_index': {'enabled': True},
        'fat_select': {'enabled': True},
        'queryset_eval': {'enabled': True},
        'drf_serializer': {'enabled': True},
        'complexity': {'enabled': True, 'threshold': 8},
    },
    'REPORTERS': ['console'],
    'IGNORE_URLS': ['/admin/', '/health/'],

    # --- Query Ignore ---
    'QUERYIGNORE_PATH': '.queryignore',  # Path to .queryignore file

    # --- Admin Dashboard ---
    'ADMIN_DASHBOARD': {
        'ENABLED': False,       # Enable the admin dashboard panel
        'MAX_REPORTS': 100,     # Max stored reports
    },

    # --- QueryTurbo (v2.0) ---
    'TURBO': {
        'ENABLED': False,              # Opt-in
        'MAX_SIZE': 1024,              # Max cached patterns
        'PREPARE_ENABLED': True,       # Prepared statements
        'PREPARE_THRESHOLD': 5,        # Hits before preparing
        'VALIDATION_THRESHOLD': 3,     # Validations before trusting (skip as_sql)
        'SKIP_RAW_SQL': True,          # Skip caching for RawSQL queries
        'SKIP_EXTRA': True,            # Skip caching for .extra() queries
        'SKIP_SUBQUERIES': True,       # Skip caching for subqueries
    },
}
```

## Celery Task Support

```python
from celery import shared_task
from query_doctor.celery_integration import diagnose_task

@shared_task
@diagnose_task
def send_weekly_report():
    users = User.objects.all()
    for user in users:
        user.profile.email  # N+1 detected and reported
```

## Async View Support

The middleware supports async views:

```python
async def my_async_view(request):
    books = await sync_to_async(list)(Book.objects.select_related("author").all())
    return JsonResponse({"count": len(books)})
```

## Custom Analyzer Plugins

```toml
# In your package's pyproject.toml
[project.entry-points."query_doctor.analyzers"]
my_analyzer = "my_package.analyzers:MyCustomAnalyzer"
```

```python
from query_doctor.analyzers.base import BaseAnalyzer

class MyCustomAnalyzer(BaseAnalyzer):
    name = "my_analyzer"

    def analyze(self, queries, models_meta=None):
        prescriptions = []
        # Your detection logic here
        return prescriptions
```

## GitHub Actions CI Integration

Add query doctor checks to your PR workflow with inline annotations:

```yaml
- name: Query Doctor CI
  run: |
    python manage.py check_queries --url /api/books/ \
      --format json --output report.json \
      --baseline .query-baseline.json \
      --fail-on-regression
```

The `ci.github` module provides:
- `format_github_annotations()` — inline `::error` / `::warning` annotations in PR diffs
- `generate_pr_comment()` — Markdown summary for PR bot comments
- `write_json_report()` — JSON output for downstream CI tools

See `examples/github-actions/query-doctor.yml` for a complete workflow.

## Baseline Snapshots

Save a baseline of known issues and only fail CI on new regressions:

```bash
# Save current state as baseline
python manage.py check_queries --save-baseline=.query-baseline.json

# On CI: compare against baseline, fail only on new issues
python manage.py check_queries --baseline=.query-baseline.json --fail-on-regression
```

The baseline uses SHA-256 hashing of issue identity (type + file + description),
ignoring line numbers so that code movement doesn't trigger false regressions.

## Prescription Grouping

Group related issues for cleaner output:

```bash
# Group by file + analyzer type (default)
python manage.py check_queries --group

# Group by root cause (same fix suggestion)
python manage.py check_queries --group=root_cause

# Group by view
python manage.py check_queries --group=view
```

## Diff-Aware CI

```bash
python manage.py check_queries --url /api/books/ --diff=main
python manage.py check_queries --url /api/books/ --diff=origin/develop
```

## .queryignore

```text
# Patterns to exclude from analysis
sql:SELECT * FROM django_session%
file:myapp/migrations/*
callsite:myapp/views.py:142
ignore:nplusone:myapp/views.py:LegacyReportView
```

### Known Limitations

**Process-local cache:** The SQL template cache is not shared across
Gunicorn workers or multiple processes. Each process maintains its own
cache.

**Django internal API dependency:** QueryTurbo monkey-patches
`SQLCompiler.execute_sql()`. This has been stable across Django 4.2–6.0
but could change in future Django major releases.

## Requirements

- Python 3.10+
- Django 4.2, 5.0, 5.1, 5.2, or 6.0
- DRF (optional, for serializer analysis)
- psycopg3 (optional, for prepared statements on PostgreSQL)
- Rich (optional, for styled console output)

```bash
pip install django-query-doctor[rich]       # Rich console output
pip install django-query-doctor[otel]       # OpenTelemetry export
pip install django-query-doctor[all]        # Everything
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

```bash
git clone https://github.com/hassanzaibhay/django-query-doctor.git
cd django-query-doctor
pip install -e ".[dev]"
pytest
```

## License

MIT
