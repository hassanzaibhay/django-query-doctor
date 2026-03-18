# Design Decisions

This document explains the key architectural decisions in django-query-doctor, the alternatives that were considered, and why the chosen approach was selected.

---

## 1. execute_wrapper Instead of Monkey-Patching

The most fundamental decision in django-query-doctor is how to intercept SQL queries. There are four viable approaches in Django:

### Comparison of Approaches

| Approach | Works without DEBUG | Composable | Officially supported | Captures all backends | Risk of breakage |
|----------|:------------------:|:----------:|:-------------------:|:--------------------:|:----------------:|
| `connection.queries` | No | N/A (read-only) | Yes | Yes | Low |
| `connection.execute_wrapper()` | Yes | Yes | Yes | Yes | Low |
| Monkey-patch `CursorWrapper.execute` | Yes | No | No | Fragile | High |
| Custom database backend | Yes | No | Partially | Per-backend | Medium |

### Why execute_wrapper Wins

**`connection.queries`** is the simplest approach, but it only works when `DEBUG=True`. Django explicitly clears the query log and disables recording when `DEBUG=False`. Since a core goal of django-query-doctor is to work in staging and production, this approach is ruled out.

**Monkey-patching `CursorWrapper.execute`** works everywhere, but it modifies Django internals in ways that can conflict with other tools (Sentry, django-silk, OpenTelemetry) and can break across Django versions when internal cursor classes are refactored.

**Custom database backends** require users to change their `DATABASES` setting, which is invasive and does not compose with other backend customizations (e.g., `django-postgrespool2`, `django-db-readonly`).

**`connection.execute_wrapper()`** is a public Django API introduced in Django 2.0. It is:

- Explicitly designed for this use case (query instrumentation)
- Composable: multiple wrappers can be stacked without conflict
- Stable across Django versions (public API contract)
- Per-connection, so it respects multi-database setups

```python
# How django-query-doctor installs its interceptor
from django.db import connection

def intercept(execute, sql, params, many, context):
    """Wrapper that captures query data without modifying execution."""
    start = time.perf_counter()
    try:
        result = execute(sql, params, many, context)
    finally:
        end = time.perf_counter()
        # Record the query for later analysis
        _store_query(sql, params, start, end)
    return result

# In middleware or context manager:
with connection.execute_wrapper(intercept):
    # All queries in this block are captured
    ...
```

> **Note:** The wrapper function must always call `execute()` and return its result. django-query-doctor never modifies the SQL, parameters, or return value. If the recording logic throws an exception, it is caught and logged --- the query still proceeds.

---

## 2. Fingerprinting Before Analysis

Queries are normalized and hashed into fingerprints *before* any analysis runs. This is a deliberate design choice, not an implementation detail.

### Why Not Analyze Raw SQL?

Raw SQL comparison would require every analyzer to independently handle:

- Parameter variation (`WHERE id = 1` vs `WHERE id = 2`)
- Whitespace differences (Django's SQL generation is not 100% consistent across backends)
- IN-list length variation (`IN (1, 2)` vs `IN (1, 2, 3, 4, 5)`)

By normalizing first, all downstream analyzers work with clean, canonical SQL strings. The benefits are:

**Single-pass normalization**: The expensive work of SQL parsing, parameter replacement, and hashing is done once. Each analyzer receives pre-processed data.

**Consistent grouping**: N+1 detection groups by fingerprint. Duplicate detection groups by fingerprint + parameters. Both use the same fingerprint, ensuring consistent behavior.

**Cheap comparisons**: SHA-256 hash comparison is O(1) per pair. Comparing raw SQL strings of varying length would be O(n) per pair.

```python
# Without fingerprinting, every analyzer would need to do this:
def is_same_query_pattern(sql1, sql2):
    normalized1 = normalize(sql1)  # Expensive
    normalized2 = normalize(sql2)  # Expensive
    return normalized1 == normalized2

# With fingerprinting, it is a simple hash lookup:
def is_same_query_pattern(q1, q2):
    return q1.fingerprint == q2.fingerprint  # O(1) string compare
```

### IN-List Normalization

A subtle but important aspect of fingerprinting is IN-list normalization. Consider:

```sql
SELECT * FROM books_book WHERE id IN (1, 2, 3)
SELECT * FROM books_book WHERE id IN (4, 5, 6, 7, 8, 9, 10)
```

These are structurally identical queries that should have the same fingerprint. Without IN-list normalization, they would hash differently because the number of `?` placeholders differs. django-query-doctor normalizes all IN-lists to `IN (?)` before hashing.

---

## 3. Stack Traces Instead of AST Parsing

To identify *where* in user code a problematic query originates, django-query-doctor captures Python stack traces at query time. An alternative approach would be to parse the Django ORM's internal AST or queryset objects.

### Trade-off Comparison

| Factor | Stack Traces | AST / QuerySet Inspection |
|--------|:------------:|:-------------------------:|
| Accuracy of file:line | High | Low (queryset may be built across multiple files) |
| Works with raw SQL | Yes | No |
| Works with third-party ORM extensions | Yes | No |
| Performance cost | ~20-40 microseconds per query | ~5-10 microseconds per query |
| Maintenance burden | Low (Python stdlib) | High (Django internals change) |
| Captures the call site | Yes | No (captures queryset definition, not evaluation) |

### Why Stack Traces

**The call site matters more than the definition site.** A queryset might be defined in a manager method but evaluated in a view, serializer, or template. The N+1 problem occurs at the *evaluation* point (where the lazy relationship is accessed), not at the definition point. Stack traces capture exactly this.

```python
# The queryset is defined here...
class BookManager(models.Manager):
    def published(self):
        return self.filter(status="published")

# ...but the N+1 happens here (in the template or serializer):
{% for book in books %}
    {{ book.author.name }}  <!-- This triggers the N+1 -->
{% endfor %}
```

AST parsing would point to the manager. Stack traces point to the template access --- which is where the fix needs to be applied.

**Raw SQL and third-party code.** Not all queries go through the ORM. Raw SQL via `connection.cursor()`, queries from third-party packages, and queries from Django's internals (e.g., auth middleware) all execute SQL without a queryset object. Stack traces capture all of these uniformly.

**Stability.** `traceback.extract_stack()` is a stable Python stdlib function. Django's internal query compilation structures (`SQLCompiler`, `Query`, `WhereNode`) are not part of Django's public API and change across versions.

> **Tip:** If stack traces are too expensive for your workload, you can disable them with `QUERY_DOCTOR["CAPTURE_STACK_TRACES"] = False`. Analysis will still work, but prescriptions will not include file:line references.

---

## 4. Per-Request Analysis, Not Background Processing

django-query-doctor runs analysis synchronously at the end of each request (or scope). An alternative would be to buffer queries and analyze them in a background thread or Celery task.

### Why Synchronous

**Immediate feedback**: When running in development, you want to see the report in your terminal immediately after the request completes. A background approach would introduce latency and require a separate log viewer.

**Simplicity**: Background processing introduces complexity: message queues, worker processes, serialization of query data, and the risk of losing data if the worker crashes.

**Low overhead**: Analysis is fast. For a typical request with 50-200 queries, the analysis phase takes 1-5ms. This is negligible compared to the request's own database time.

**No external dependencies**: Background processing would require Celery, Redis, or a similar queue. django-query-doctor has zero required dependencies beyond Django.

### When Background Makes Sense

For the management command `diagnose_queries`, which scans every URL in the project, analysis *is* batched and can be parallelized. But this is a CLI tool, not a request-time feature.

---

## 5. Prescriptions, Not Just Warnings

Every issue detected by django-query-doctor results in a `Prescription` object that includes not just the problem description, but also the exact fix.

### Why This Matters

Most query analysis tools stop at detection:

```
WARNING: 47 duplicate queries detected for table books_author
```

This tells the developer *what* is wrong but leaves them to figure out *why* and *how to fix it*. In a large codebase, finding the right queryset to modify, determining whether to use `select_related` or `prefetch_related`, and knowing which relationships to include can take significant time.

django-query-doctor goes further:

```
N+1 DETECTED: 47 queries on books_author via FK author_id

  Source: myapp/serializers.py:12
  Fix:    Add select_related('author') to queryset at myapp/views.py:8
          - Book.objects.all()
          + Book.objects.select_related('author')
```

### How Fixes Are Generated

The fixer module uses a combination of:

1. **Stack trace analysis**: Identifies the queryset definition site (where `.all()`, `.filter()`, etc. are called).
2. **SQL pattern matching**: Determines whether the issue is a FK access (`select_related`) or M2M access (`prefetch_related`).
3. **Django model introspection**: Resolves the relationship name from the database column name (e.g., `author_id` column maps to `author` relationship on the `Book` model).
4. **Code generation**: Produces the modified queryset call as a string.

```python
# The fixer knows that:
# - books_author table is accessed via author_id column
# - author_id is a ForeignKey on Book model
# - The relationship name is "author"
# - ForeignKey access is optimized with select_related()
# - The queryset is defined at myapp/views.py:8

# So it generates:
fix = 'Book.objects.select_related("author")'
```

---

## 6. Optional Dependencies Only

django-query-doctor has exactly one required dependency: Django itself.

### The Rich Dilemma

Rich produces beautiful terminal output with colors, tables, and panels. It dramatically improves the developer experience of reading query reports. However, making it a hard dependency would:

- Add ~3MB to the install size
- Introduce a transitive dependency tree (pygments, markdown-it-py, etc.)
- Potentially conflict with other versions of Rich already in the project

The solution is an optional dependency with a graceful fallback:

```python
# reporters/console.py
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


def print_report(prescriptions):
    """Print prescriptions to the console."""
    if HAS_RICH:
        _print_rich(prescriptions)
    else:
        _print_plain(prescriptions)
```

The plain text fallback contains all the same information, just without colors and formatting.

### Install With Rich

```bash
pip install django-query-doctor[rich]
```

This pattern follows the precedent set by Django itself (e.g., `django[argon2]`, `django[bcrypt]`).

---

## 7. Never Crash the Host Application

This is not just a guideline --- it is an invariant enforced throughout the codebase. django-query-doctor wraps all analysis and reporting code in try/except blocks:

```python
# middleware.py
class QueryDoctorMiddleware:
    def __call__(self, request):
        try:
            # Install interceptor
            with connection.execute_wrapper(intercept):
                response = self.get_response(request)
            # Analyze and report
            _analyze_and_report(request)
        except Exception:
            logger.warning(
                "django-query-doctor encountered an error; "
                "request processing was not affected.",
                exc_info=True,
            )
            # If we haven't gotten the response yet, get it now
            if "response" not in locals():
                response = self.get_response(request)
        return response
```

### Why This Is Non-Negotiable

django-query-doctor is a diagnostic tool. It must never interfere with the application it is diagnosing. If a bug in our code causes an exception, the user's request must still be served. The worst case for a django-query-doctor failure is a missing report --- never a 500 error returned to the end user.

> **Warning:** If you are developing a custom analyzer and it raises an unhandled exception, the exception will be caught and logged. Your analyzer will effectively be skipped for that request. Check your Django logs for `query_doctor` warnings if your custom analyzer does not seem to be producing output.

---

## Summary

| Decision | Chosen Approach | Key Reason |
|----------|----------------|------------|
| Query interception | `execute_wrapper()` | Stable public API, works without DEBUG, composable |
| Pre-processing | Fingerprint before analysis | Single-pass normalization, O(1) comparisons |
| Source location | Stack traces | Captures call site, works with raw SQL |
| Analysis timing | Synchronous per-request | Immediate feedback, zero external deps |
| Output format | Prescriptions with fixes | Actionable, not just informational |
| Dependencies | Optional only | Minimal footprint, no conflicts |
| Error handling | Never crash host app | Diagnostic tool must be invisible on failure |

For the performance implications of these decisions, see [Performance](./performance.md). For how these decisions compare to other tools, see [Comparison](./comparison.md).
