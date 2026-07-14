# Async Support

django-query-doctor supports async Django views and ASGI deployments through its middleware. This page covers what works in async contexts -- and what does not.

---

## ASGI Middleware Auto-Detection

When your Django application is served via ASGI (using Daphne, Uvicorn, Hypercorn, or similar), `QueryDoctorMiddleware` automatically detects the ASGI environment and switches to its async implementation (`sync_capable` and `async_capable` are both enabled). No additional configuration is needed:

```python title="settings.py"
MIDDLEWARE = [
    ...,
    "query_doctor.middleware.QueryDoctorMiddleware",  # Works for both WSGI and ASGI
]
```

Under ASGI, the middleware:

- Uses `contextvars.ContextVar` for async safety, ensuring correct isolation across concurrent coroutines on the same thread.
- Awaits the response before running analyzers.
- Works correctly with Django's async-to-sync and sync-to-async bridge functions.

Async views analyzed by the middleware need nothing special:

```python title="myapp/views.py"
async def book_list(request):
    """Async view -- queries captured by the middleware."""
    books = [book async for book in Book.objects.select_related("author").all()]
    return JsonResponse({"books": [{"title": b.title} for b in books]})
```

---

## Django Async ORM Methods

Django's async ORM methods (`aget`, `acreate`, `acount`, `aexists`, async iteration) ultimately execute through the same database connection as their sync counterparts, so the interceptor's `execute_wrapper` captures them identically. Async iteration over querysets is captured the same way.

---

## The Context Manager in Async Code

`diagnose_queries()` is a **synchronous** context manager. Use it with a plain `with` statement -- including inside `async def` functions:

```python
from query_doctor.context_managers import diagnose_queries


async def process_books():
    with diagnose_queries() as report:
        count = await Book.objects.acount()
        book = await Book.objects.select_related("author").aget(pk=1)
        exists = await Book.objects.filter(published=True).aexists()

    # report.total_queries == 3
    # Prescriptions are generated normally
```

> **Not supported:** `async with diagnose_queries()` raises a `TypeError` -- the context manager does not implement the async context manager protocol.

---

## The `@diagnose` Decorator and Async Views

> **Not supported:** `@diagnose` does not detect or await coroutine functions. Applied to an `async def` view, the wrapped call returns the coroutine object and the capture context exits before the view body runs, so nothing useful is captured.

For async views, use the middleware (recommended) or a `with diagnose_queries():` block inside the view body.

---

## Mixed Sync/Async Code

Django allows mixing sync and async code using `sync_to_async` and `async_to_sync`. Queries made in a `sync_to_async`-wrapped helper are captured because the interceptor is installed at the database connection level, which is shared across sync and async execution within the same request:

```python
from asgiref.sync import sync_to_async


async def mixed_view(request):
    # Async ORM call -- captured
    book = await Book.objects.aget(pk=1)

    # Sync function called from async context -- also captured
    related_books = await sync_to_async(get_related_books)(book)

    return JsonResponse({"book": book.title, "related": len(related_books)})


def get_related_books(book):
    """Sync helper -- queries here are still captured."""
    return list(Book.objects.filter(author=book.author).exclude(pk=book.pk))
```

---

## Limitations

- **`@diagnose` / `@query_budget` on coroutines**: not supported (see above).
- **Connection pooling**: If you use a third-party connection pooler (like `django-db-connection-pool`), ensure it is compatible with Django's `execute_wrapper` mechanism.
- **Raw async drivers**: Queries issued directly through non-Django drivers (e.g. `asyncpg`) bypass Django's connection and are not captured.

---

## Further Reading

- [Middleware](middleware.md) -- General middleware configuration.
- [Celery Support](celery.md) -- Using with Celery tasks (which are not async views).
- [How It Works](how-it-works.md) -- The full pipeline overview.
