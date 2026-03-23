# Frequently Asked Questions

---

## General

### Does django-query-doctor require DEBUG=True?

No. django-query-doctor uses `connection.execute_wrapper()` to intercept
queries, which works regardless of the `DEBUG` setting. This is a deliberate
design decision -- unlike `connection.queries`, which only populates when
`DEBUG=True`, the execute wrapper approach works in any environment.

```python
# This works with DEBUG=False
QUERY_DOCTOR = {
    "ENABLED": True,
}
```

!!! tip "Production usage"
    While the package works without `DEBUG=True`, we recommend running it
    primarily in development and CI. Use management commands like
    `check_queries` in CI rather than the middleware in production. See
    [Examples](examples/index.md) for production
    patterns.

### What is the performance overhead?

The overhead depends on your configuration:

| Mode | Overhead | Recommendation |
|------|----------|----------------|
| Middleware (all analyzers) | 5-15 ms per request | Development only |
| Middleware (N+1 only) | 2-5 ms per request | Development only |
| Context manager | Only during the `with` block | Any environment |
| Management commands | Zero runtime overhead | CI/CD |

The primary cost is capturing stack traces for each query. You can reduce
overhead by:

- Disabling stack trace capture: `"CAPTURE_TRACEBACKS": False`
- Reducing the sample rate: `"SAMPLE_RATE": 0.1`
- Excluding paths: `"EXCLUDE_PATHS": ["/admin/", "/static/"]`

### Will django-query-doctor crash my application?

No. All analysis code is wrapped in `try/except`. If an error occurs in the
analysis pipeline, it is logged as a warning and the request proceeds normally.
This is a core design principle -- the package never interferes with your
application's functionality.

---

## Compatibility

### Does it work with the repository pattern?

Yes. django-query-doctor intercepts queries at the database connection level,
below any application-level abstraction. Whether you use the repository
pattern, service layers, or direct ORM calls, the interception works the same
way.

The stack tracer maps queries back to your source code regardless of how many
abstraction layers sit between the view and the ORM call.

### Can it detect N+1 queries caused by model @property methods?

Yes. When a `@property` method on a model accesses a related object, the
resulting query is intercepted just like any other ORM query. The stack trace
will point to the line in the property method where the related access occurs:

```python
class Book(models.Model):
    author = models.ForeignKey(Author, on_delete=models.CASCADE)

    @property
    def author_name(self):
        return self.author.name  # This triggers a query, detected as N+1
```

The prescription will reference the property method and suggest adding
`select_related('author')` to the queryset that loads the books.

### Does it support Celery tasks?

Yes. Use the `@diagnose_task` decorator to analyze queries within Celery tasks:

```python
from query_doctor.decorators import diagnose_task

@diagnose_task
@app.task
def process_orders():
    orders = Order.objects.all()
    for order in orders:
        order.customer.notify()  # N+1 detected
```

Install with Celery extras for full support:

```bash
pip install django-query-doctor[celery]
```

### Does it support async Django views and ASGI?

Yes. django-query-doctor provides an async-compatible middleware that works
with Django's ASGI support:

```python title="settings.py"
MIDDLEWARE = [
    ...,
    "query_doctor.middleware.QueryDoctorMiddleware",  # Works with both WSGI and ASGI
]
```

The middleware automatically detects whether it is running in sync or async
mode and uses the appropriate execution path.

!!! note "Async ORM queries"
    Django's async ORM methods (e.g., `await Book.objects.aget()`) are
    intercepted in the same way as sync queries. The underlying database
    calls still go through the execute wrapper.

---

## Comparison with Other Tools

### How does it compare to django-debug-toolbar?

| Feature | django-query-doctor | django-debug-toolbar |
|---------|--------------------|--------------------|
| Shows query count | Yes | Yes |
| Shows query SQL | Yes | Yes |
| Shows query time | Yes | Yes |
| Detects N+1 patterns | Yes | No |
| Detects duplicate queries | Yes | Partial (shows count) |
| Suggests fixes | Yes (exact code) | No |
| File:line references | Yes | No |
| Works without DEBUG | Yes | No |
| CI/CD integration | Yes (JSON, exit codes) | No |
| Auto-fix mode | Yes | No |
| Celery support | Yes | No |
| Production-safe | Yes | No |

!!! info "Complementary tools"
    django-query-doctor and django-debug-toolbar serve different purposes.
    The toolbar is an interactive debugging panel for exploring request data.
    django-query-doctor is an automated diagnostic tool that produces
    prescriptive fixes. They can be used together.

### How does it compare to nplusone?

| Feature | django-query-doctor | nplusone |
|---------|--------------------|--------------------|
| N+1 detection | Yes | Yes |
| Duplicate detection | Yes | No |
| Missing index detection | Yes | No |
| Fat SELECT detection | Yes | No |
| DRF-specific analysis | Yes | No |
| Fix suggestions | Yes (exact code) | No |
| Multiple reporters | 5 | 1 (logging) |
| Management commands | 4 | 0 |
| Auto-fix mode | Yes | No |

---

## Analyzers

### Can I write custom analyzers?

Yes. Subclass `BaseAnalyzer` and register your analyzer through Django settings
or Python entry points:

```python title="myapp/analyzers.py"
from query_doctor.analyzers.base import BaseAnalyzer, Prescription


class SlowJoinAnalyzer(BaseAnalyzer):
    """Detects queries with slow JOIN patterns."""

    def analyze(self, queries):
        prescriptions = []
        for query in queries:
            if self._has_slow_join(query):
                prescriptions.append(Prescription(
                    severity="warning",
                    issue="Query uses a slow cross-join pattern",
                    location=query.location,
                    suggestion="Rewrite using subquery or EXISTS",
                    analyzer="SlowJoinAnalyzer",
                ))
        return prescriptions
```

Register it in settings:

```python title="settings.py"
QUERY_DOCTOR = {
    "EXTRA_ANALYZERS": [
        "myapp.analyzers.SlowJoinAnalyzer",
    ],
}
```

Or register via entry points in `pyproject.toml`:

```toml title="pyproject.toml"
[project.entry-points."query_doctor.analyzers"]
slow_join = "myapp.analyzers:SlowJoinAnalyzer"
```

See [Contributing](contributing.md) for a full walkthrough of adding an
analyzer.

### Does auto-fix modify my code automatically?

The `fix_queries` management command can apply fixes, but it operates with
safety guardrails:

1. **Dry run by default** -- you must explicitly pass `--apply` to make changes
2. **Backup files** -- `.bak` files are created before any modifications
3. **Limited scope** -- only `select_related` and `prefetch_related` additions
   are auto-applied. Complex fixes (annotations, restructuring) are suggested
   but not auto-applied.

```bash
# Preview what would change
python manage.py fix_queries --dry-run

# Apply changes with backups
python manage.py fix_queries --apply
```

!!! warning "Review auto-fixes"
    Always review auto-applied changes before committing. The tool makes
    conservative suggestions, but edge cases in your codebase may require
    manual adjustment.

---

## Troubleshooting

### No prescriptions are showing up

Check these common causes:

1. **Middleware not installed** -- verify `"query_doctor.middleware.QueryDoctorMiddleware"` is in your `MIDDLEWARE` setting
2. **Package disabled** -- check that `QUERY_DOCTOR["ENABLED"]` is `True` (or not set, as it defaults to `True`)
3. **Path excluded** -- check `QUERY_DOCTOR["EXCLUDE_PATHS"]` does not match your URL
4. **Severity filter too high** -- lower `MIN_SEVERITY` to `"DEBUG"` to see all issues
5. **No issues exist** -- your code may already be well-optimized

### Prescriptions point to the wrong file/line

The stack tracer excludes Django internals and third-party packages to find
the first frame in your application code. If the reported location seems wrong:

1. Check if the query originates from a middleware or signal handler
2. Verify your project's source root is correctly detected
3. Try enabling verbose mode to see the full stack trace:
   ```python
   QUERY_DOCTOR = {
       "CONSOLE_VERBOSITY": "verbose",
   }
   ```

### Too many prescriptions in a large project

See [Examples](examples/index.md) for techniques
including diff-aware mode, `.queryignore`, per-app scanning, and gradual
rollout.
