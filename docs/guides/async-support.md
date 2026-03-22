# Async Support

django-query-doctor fully supports Django's async views, async ORM methods, and ASGI deployments. This page covers how to use query analysis in async contexts.

---

## Async Views with the Decorator

Use the `@diagnose` decorator on async views the same way you would on sync views. The decorator automatically detects whether the wrapped function is a coroutine and adapts its behavior:

```python title="myapp/views.py"
from query_doctor.decorators import diagnose


@diagnose
async def book_list(request):
    """Async view that lists books."""
    books = [book async for book in Book.objects.select_related("author").all()]
    return JsonResponse({"books": [{"title": b.title} for b in books]})
```

The decorator installs an async-compatible query interceptor that captures all database calls made within the coroutine, including those made by Django's async ORM methods.

### Class-Based Async Views

For async class-based views, apply the decorator to the `dispatch` method:

```python title="myapp/views.py"
from django.utils.decorators import method_decorator
from django.views import View
from query_doctor.decorators import diagnose


@method_decorator(diagnose, name="dispatch")
class AsyncBookListView(View):
    async def get(self, request):
        books = [book async for book in Book.objects.all()]
        return JsonResponse({"books": [{"title": b.title} for b in books]})
```

---

## ASGI Middleware Auto-Detection

When your Django application is served via ASGI (using Daphne, Uvicorn, Hypercorn, or similar), `QueryDoctorMiddleware` automatically detects the ASGI environment and switches to its async implementation. No additional configuration is needed.

```python title="settings.py"
MIDDLEWARE = [
    ...,
    "query_doctor.middleware.QueryDoctorMiddleware",  # Works for both WSGI and ASGI
]
```

Under ASGI, the middleware:

- Uses `contextvars.ContextVar` for async safety, ensuring correct isolation across concurrent coroutines. Both QueryTurbo context managers and the query interceptor use `contextvars.ContextVar`, making the full capture pipeline safe for ASGI deployments with concurrent requests on the same thread.
- Installs an async `execute_wrapper` on the database connection.
- Awaits the response before running analyzers.
- Works correctly with Django's async-to-sync and sync-to-async bridge functions.

---

## Django Async ORM Methods

Django's async ORM methods (`aget`, `afilter`, `acreate`, `acount`, `aexists`, etc.) are fully supported. django-query-doctor captures queries made through these methods identically to their sync counterparts:

```python
from query_doctor.context_managers import diagnose_queries


async def process_books():
    async with diagnose_queries() as report:
        count = await Book.objects.acount()
        book = await Book.objects.select_related("author").aget(pk=1)
        exists = await Book.objects.filter(published=True).aexists()

    # report.query_count == 3
    # Prescriptions are generated normally
```

### Async Iteration

Async iteration over querysets is captured:

```python
async with diagnose_queries() as report:
    async for book in Book.objects.select_related("author").all():
        print(book.title, book.author.name)

# All queries from the async iterator are captured
```

---

## Async Context Manager

The `diagnose_queries()` context manager works as both a sync and async context manager:

```python
# Sync usage
with diagnose_queries() as report:
    books = list(Book.objects.all())

# Async usage
async with diagnose_queries() as report:
    books = [b async for b in Book.objects.all()]
```

Both produce the same `report` object with the same attributes.

---

## Mixed Sync/Async Code

Django allows mixing sync and async code using `sync_to_async` and `async_to_sync`. django-query-doctor handles these transitions correctly:

```python
from asgiref.sync import sync_to_async
from query_doctor.decorators import diagnose


@diagnose
async def mixed_view(request):
    # Async ORM call
    book = await Book.objects.aget(pk=1)

    # Sync function called from async context
    related_books = await sync_to_async(get_related_books)(book)

    return JsonResponse({"book": book.title, "related": len(related_books)})


def get_related_books(book):
    """Sync helper -- queries here are still captured."""
    return list(Book.objects.filter(author=book.author).exclude(pk=book.pk))
```

Queries made in the `sync_to_async` wrapped function are captured because the interceptor is installed at the database connection level, which is shared across sync and async contexts within the same request.

---

## Limitations

- **Connection pooling**: If you use a third-party connection pooler (like `django-db-connection-pool`), ensure it is compatible with Django's `execute_wrapper` mechanism. Most poolers are compatible, but some may require configuration.
- **Multi-database**: Async support works with Django's multi-database routing. The interceptor is installed on each database connection individually.

---

## Further Reading

- [Middleware](middleware.md) -- General middleware configuration.
- [Celery Support](celery.md) -- Using with Celery tasks (which are not async views).
- [How It Works](how-it-works.md) -- The full pipeline overview.
