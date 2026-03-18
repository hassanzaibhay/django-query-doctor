# Middleware

The `QueryDoctorMiddleware` is the simplest way to enable django-query-doctor. Once added, every HTTP request is automatically intercepted, analyzed, and reported.

---

## Setup

Add `query_doctor.middleware.QueryDoctorMiddleware` to your `MIDDLEWARE` list in `settings.py`:

```python title="settings.py"
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Add query-doctor LAST (or near last)
    "query_doctor.middleware.QueryDoctorMiddleware",
]
```

> **Placement matters.** The middleware should be placed **after** Django's core middleware. It wraps the database connection for the duration of the request, so any middleware above it in the list will have its queries captured. Placing it too early may cause issues with session or auth middleware that need unmodified database access.

---

## How It Works

On each request, the middleware performs the following steps:

1. **Wraps the connection** -- Installs an `execute_wrapper` on the default database connection. This captures every SQL statement, its parameters, execution time, and full Python stack trace.
2. **Lets the view execute** -- The request proceeds through the view layer normally. All queries are silently recorded.
3. **Runs analyzers** -- After the response is generated, captured queries are fingerprinted and passed through all enabled analyzers (N+1, duplicate, missing index, etc.).
4. **Passes to reporters** -- Any prescriptions produced by the analyzers are formatted by the configured reporters (console, JSON, log, etc.) and output.
5. **Removes the wrapper** -- The connection wrapper is removed, leaving no overhead for subsequent requests.

The middleware uses `threading.local()` to store per-request state, so it is fully thread-safe under WSGI.

---

## Excluding Paths

Not every endpoint needs analysis. Static files, health checks, and admin pages often generate noise. Use the `EXCLUDE_PATHS` setting to skip them:

```python title="settings.py"
QUERY_DOCTOR = {
    "EXCLUDE_PATHS": [
        "/static/",
        "/media/",
        "/health/",
        "/admin/jsi18n/",
        "/__debug__/",  # django-debug-toolbar
    ],
}
```

Paths are matched by prefix. If the request path starts with any entry in `EXCLUDE_PATHS`, the middleware skips interception entirely.

---

## Performance Impact

The middleware adds a small overhead to each request:

- **Interception** -- Recording each query adds approximately 0.05ms per query. For a typical request with 20 queries, that is roughly 1ms total.
- **Analysis** -- Running all 7 analyzers over captured queries typically takes 1-5ms, depending on the number of unique fingerprints.
- **Reporting** -- Console output adds minimal time. JSON and HTML reporters write to buffers, not disk, during the request.

For most development and staging workloads, this overhead is negligible. For production use, consider the approaches below.

> **Tip:** If you need production-safe analysis, use the `SAMPLE_RATE` setting to analyze only a percentage of requests:
>
> ```python
> QUERY_DOCTOR = {
>     "SAMPLE_RATE": 0.1,  # Analyze 10% of requests
> }
> ```

---

## Recommended Workflow for Large Codebases

For large projects with hundreds of endpoints, running the middleware on every request during development can produce a lot of output. A more practical approach:

1. **Turn off the middleware** -- Remove it from `MIDDLEWARE` or set `"ENABLED": False`.
2. **Use management commands** -- Run `check_queries` or `diagnose_project` against specific URLs or the entire project (see [Management Commands](management-commands.md)).
3. **Target hot spots** -- Use the `@diagnose` decorator or `diagnose_queries()` context manager on specific views you are actively optimizing.
4. **Re-enable for validation** -- Turn the middleware back on to verify your fixes work across the full request lifecycle.

---

## Alternatives to the Middleware

You do not need the middleware to use django-query-doctor. Two alternatives allow fine-grained control.

### The `@diagnose` Decorator

Apply the `@diagnose` decorator to individual views or functions:

```python title="views.py"
from query_doctor.decorators import diagnose


@diagnose
def book_list(request):
    books = Book.objects.all()
    return render(request, "books/list.html", {"books": books})
```

For class-based views, apply it to `dispatch` or use `method_decorator`:

```python title="views.py"
from django.utils.decorators import method_decorator
from query_doctor.decorators import diagnose


@method_decorator(diagnose, name="dispatch")
class BookListView(ListView):
    model = Book
```

The decorator accepts the same options as the middleware settings:

```python
@diagnose(severity="WARNING", analyzers=["nplusone", "duplicate"])
def my_view(request):
    ...
```

### The `diagnose_queries()` Context Manager

For even more targeted analysis, wrap specific blocks of code:

```python title="views.py"
from query_doctor.context_managers import diagnose_queries


def book_detail(request, pk):
    with diagnose_queries() as report:
        book = Book.objects.select_related("author").get(pk=pk)
        related = Book.objects.filter(author=book.author)

    # report.prescriptions contains any issues found
    # report.query_count contains the total number of queries
    return render(request, "books/detail.html", {
        "book": book,
        "related": related,
    })
```

The context manager is particularly useful in management commands, Celery tasks, and tests where the middleware is not active.

---

## Disabling the Middleware

To temporarily disable analysis without removing the middleware from your settings:

```python title="settings.py"
QUERY_DOCTOR = {
    "ENABLED": False,
}
```

Or use an environment variable pattern:

```python title="settings.py"
import os

QUERY_DOCTOR = {
    "ENABLED": os.environ.get("QUERY_DOCTOR_ENABLED", "false").lower() == "true",
}
```

---

## Further Reading

- [How It Works](how-it-works.md) -- Full pipeline overview.
- [Management Commands](management-commands.md) -- Run analysis without the middleware.
- [Configuration](../getting-started/configuration.md) -- All available settings.
