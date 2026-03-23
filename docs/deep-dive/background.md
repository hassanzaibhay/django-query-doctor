# Background & Design Decisions

Why django-query-doctor exists, the problems it solves, and the key architectural decisions that shape it.

---

## The Problem

The N+1 query problem is the most common performance issue in Django applications. Code fetches a list of objects, then individually queries related objects one at a time — turning 2 queries into hundreds:

```python
class BookListView(generics.ListAPIView):
    queryset = Book.objects.all()  # No select_related
    serializer_class = BookSerializer  # Accesses author, publisher, categories
```

With 50 books: **151 queries instead of 3.** The fix is a one-line `select_related` call, but you have to know the problem exists first.

In a typical Django project with 100+ models, these inefficiencies accumulate silently. Existing tools help find them but fall short of fixing them:

| Tool | Limitation |
|------|-----------|
| django-debug-toolbar | Requires `DEBUG=True`, manual inspection, no CI integration, no fix suggestions |
| django-silk | Heavyweight (own DB tables), detection only, not CI-friendly |
| nplusone | N+1 only (no duplicates, indexes, etc.), no file:line, no fixes, unmaintained |
| django-auto-prefetch | Masks the problem instead of fixing it, ForeignKey only, no visibility |

django-query-doctor addresses all of these gaps: 8 analyzer categories, exact file:line references, copy-paste code fixes, CI integration, and no `DEBUG=True` requirement.

---

## Key Design Decisions

### 1. execute_wrapper, Not Monkey-Patching

`connection.execute_wrapper()` is Django's public API for query instrumentation. Unlike monkey-patching `CursorWrapper.execute`, it composes with other wrappers (Sentry, OTel), works without `DEBUG=True`, and is stable across Django versions.

### 2. Fingerprint Before Analysis

Queries are normalized (parameters replaced with `?`, whitespace collapsed, IN-lists normalized) and SHA-256 hashed before any analyzer runs. This gives all downstream analyzers clean, canonical SQL with O(1) comparisons. N+1 detection groups by fingerprint; duplicate detection groups by fingerprint + parameters.

### 3. Stack Traces for Source Location

Stack traces capture *where the query was triggered* (the evaluation site), not where the queryset was defined. A queryset defined in a manager but evaluated in a template — the stack trace points to the template, where the fix belongs.

Trade-off: ~20-40 μs per query. Disable with `CAPTURE_STACK_TRACES: False` if needed.

### 4. Prescriptions, Not Just Warnings

Every issue produces a `Prescription` with the problem description AND the exact code fix:

```
N+1 DETECTED: 47 queries on books_author via FK author_id
  Source: myapp/serializers.py:12
  Fix:    Add select_related('author') to queryset at myapp/views.py:8
          - Book.objects.all()
          + Book.objects.select_related('author')
```

The fixer uses stack trace analysis, SQL pattern matching, and Django model introspection to generate the fix.

### 5. Per-Request Synchronous Analysis

Analysis runs at the end of each request (or scope), not in a background worker. For a typical 50-200 query request, analysis takes 1-5ms — negligible compared to DB time. No external dependencies (Celery, Redis) needed.

### 6. Optional Dependencies Only

The only runtime dependency is Django. Rich (console formatting), DRF (serializer analysis), psycopg3 (prepared statements), and OpenTelemetry are all optional:

```python
try:
    from rich.console import Console
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
```

### 7. Never Crash the Host App

All analysis and reporting code is wrapped in try/except. If django-query-doctor encounters an internal error, it logs a warning and lets the request proceed. The worst case is a missing report — never a 500 error.

---

## Decision Summary

| Decision | Approach | Reason |
|----------|---------|--------|
| Query interception | `execute_wrapper()` | Stable public API, composable, works without DEBUG |
| Pre-processing | Fingerprint before analysis | Single-pass normalization, O(1) comparisons |
| Source location | Stack traces | Captures call site, works with raw SQL |
| Analysis timing | Synchronous per-request | Immediate feedback, zero external deps |
| Output format | Prescriptions with fixes | Actionable, not just informational |
| Dependencies | Optional only | Minimal footprint, no conflicts |
| Error handling | Never crash host app | Diagnostic tool must be invisible on failure |

---

## Next Steps

- [Architecture](./architecture.md) — the four-stage pipeline in detail
- [Performance & Benchmarks](./performance.md) — overhead measurements
- [Comparison with Alternatives](./comparison.md) — feature-by-feature comparison
