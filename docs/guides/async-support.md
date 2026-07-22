# Async Support

django-query-doctor supports async Django views and ASGI deployments through its middleware. This page covers what works in async contexts -- and what does not.

---

## ASGI Support

When your Django application is served via ASGI (Daphne, Uvicorn, Hypercorn, or similar), `QueryDoctorMiddleware` captures queries with no additional configuration:

```python title="settings.py"
MIDDLEWARE = [
    ...,
    "query_doctor.middleware.QueryDoctorMiddleware",  # Works for both WSGI and ASGI
]
```

### How capture works under ASGI

The middleware declares `sync_capable = True` and `async_capable = False`. Django adapts sync-only middleware with `sync_to_async(thread_sensitive=True)`, which runs it in the same thread-sensitive executor Django uses for **all** synchronous ORM work — including the ORM calls made inside `async def` views, which Django routes through that same executor.

That co-location is the mechanism. Django keeps database connections in thread-local storage, so the `execute_wrapper` the middleware installs is only visible to queries issued on the same thread. Running the middleware in the executor thread puts the wrapper on the connection object the ORM actually uses.

This is how Django adapts *every* sync-only middleware under ASGI. It is not a query-doctor-specific compromise.

Under Django's ASGI handler it also costs no request concurrency: `ASGIHandler` opens a separate `ThreadSensitiveContext` per request (`django/core/handlers/asgi.py`), and asgiref allocates one executor thread per such context, so requests do not serialise against one another. This covers normal deployments — `get_asgi_application()` returns an `ASGIHandler`, and the `application` object in a project's `asgi.py` is what Daphne, Uvicorn, Hypercorn and other ASGI servers serve.

Code that reaches the middleware chain *without* going through `ASGIHandler` — `django.test.AsyncClient`, which calls `get_response_async()` directly — gets no such context, and asgiref falls back to a single process-wide executor thread. Requests do serialise there. Capture still works; only concurrency differs.

!!! note "Effect on your own middleware"

    Django assigns middleware modes from the inside out, so every middleware listed **before** `QueryDoctorMiddleware` in `MIDDLEWARE` runs in sync mode too. With the recommended last position, that is the whole chain.

    This is ordinary Django behaviour for any sync-only middleware, and much third-party middleware is sync-only, so most stacks are already in this situation. It does not affect request concurrency. But if you maintain async-capable middleware of your own, it will run synchronously while query-doctor is installed.

    This is not a change relative to 2.1.1. The missing coroutine marker in 2.0.0–2.1.1 (see the warning below) already forced those middleware into sync mode, while additionally breaking them.

Under ASGI, the middleware:

- Runs analyzers after the view returns, in the executor thread.
- Captures queries from `async def` views and from sync views alike.
- Captures queries issued inside `sync_to_async`-wrapped helpers.

!!! warning "Broken before 2.1.2"

    Versions 2.0.0 through 2.1.1 declared `async_capable = True`. Under ASGI this produced one of two symptoms:

    - **Every request failed** with `TypeError: object HttpResponse can't be used in 'await' expression` (or `HttpResponseServerError` when `DEBUG = False`), raised at `django/core/handlers/base.py` in `get_response_async`. This happened whenever any middleware listed *before* query-doctor touched the response object — which includes `SecurityMiddleware`, `CommonMiddleware`, and `XFrameOptionsMiddleware`, so the `startproject` defaults were always affected.
    - **Requests succeeded but reported nothing.** In stacks that did not crash, the middleware ran on the event loop thread while the ORM ran in the executor thread, so it wrapped a connection object the queries never touched.

    If you are on an affected version, upgrade to 2.1.2. Any `async_capable = False` subclass workaround you applied becomes redundant, but remains harmless.

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

!!! danger "`diagnose_queries()` captures nothing inside an `async def` function"

    Measured on Django 6.0 under a real ASGI handler: a `with diagnose_queries():` block inside an `async def` view reports **zero queries**, however many the block issues.

    The cause is the same thread-locality described above, applied to the context manager instead of the middleware. The `with` block runs on the event loop thread and installs its `execute_wrapper` on *that* thread's connection object. The ORM work inside it is routed to the thread-sensitive executor on a different thread, which resolves to a different connection. The wrapper never sees the queries.

    `contextvars` do not help here. The interceptor's per-instance `ContextVar` storage is correct and does propagate across `await` -- but Django's connection registry is thread-local, not context-local, so the wrapper is on the wrong object before contextvars are ever consulted.

    Use the **middleware** to diagnose async views. It is adapted into the executor thread by Django and captures correctly.

`diagnose_queries()` is a **synchronous** context manager and works as documented in synchronous code -- including inside a `def` view served under ASGI, where Django runs the whole view in the executor thread:

```python
from query_doctor.context_managers import diagnose_queries


def process_books(request):
    with diagnose_queries() as report:
        books = list(Book.objects.select_related("author").all())

    # report.total_queries reflects the queries above
    # Prescriptions are generated normally
```

> **Not supported:** `async with diagnose_queries()` raises a `TypeError` -- the context manager does not implement the async context manager protocol.

---

## The `@diagnose` Decorator and Async Views

> **Not supported:** `@diagnose` does not detect or await coroutine functions. Applied to an `async def` view, the wrapped call returns the coroutine object and the capture context exits before the view body runs, so nothing useful is captured.

For async views, use the middleware. A `with diagnose_queries():` block inside an `async def` view body does not work either -- see the warning above.

---

## Mixed Sync/Async Code

Django allows mixing sync and async code using `sync_to_async` and `async_to_sync`. Queries made in a `sync_to_async`-wrapped helper are captured because that helper runs in the same thread-sensitive executor the middleware itself was adapted into (see [How capture works under ASGI](#how-capture-works-under-asgi)), so it resolves to the same thread-local connection object the interceptor is installed on:

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
