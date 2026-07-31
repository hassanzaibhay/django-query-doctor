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

That co-location is the mechanism. Django keeps database connections in thread-local storage ([Django docs: Databases — connection handling](https://docs.djangoproject.com/en/stable/ref/databases/#connection-management), and `django.db.utils.ConnectionHandler`, which subclasses asgiref's `Local`), so the `execute_wrapper` the middleware installs is only visible to queries issued on the same thread. Running the middleware in the executor thread puts the wrapper on the connection object the ORM actually uses.

This is Django's standard adaptation for any middleware that declares `async_capable = False`, not a query-doctor-specific compromise — see [Django docs: Asynchronous support — Async middleware](https://docs.djangoproject.com/en/stable/topics/async/#async-middleware) and `django.core.handlers.base.BaseHandler.load_middleware`, which wraps such middleware in `sync_to_async(thread_sensitive=True)`.

Under Django's ASGI handler it also costs no request concurrency: `ASGIHandler` opens a separate `ThreadSensitiveContext` per request (`django/core/handlers/asgi.py`), and asgiref allocates one executor thread per such context, so requests do not serialise against one another. This covers normal deployments — `get_asgi_application()` returns an `ASGIHandler`, and the `application` object in a project's `asgi.py` is what Daphne, Uvicorn, Hypercorn and other ASGI servers serve.

Code that reaches the middleware chain *without* going through `ASGIHandler` — `django.test.AsyncClient`, which calls `get_response_async()` directly — gets no such context, and asgiref falls back to a single process-wide executor thread. Requests do serialise there. Capture still works; only concurrency differs.

!!! note "Effect on your own middleware"

    Django assigns middleware modes from the inside out, so every middleware listed **before** `QueryDoctorMiddleware` in `MIDDLEWARE` runs in sync mode too. With the recommended last position, that is the whole chain.

    This is ordinary Django behaviour for any sync-only middleware, and much third-party middleware is sync-only, so most stacks are already in this situation. It does not affect request concurrency. But if you maintain async-capable middleware of your own, it will run synchronously while query-doctor is installed.

    This is not a change relative to 2.1.1. The missing coroutine marker in 2.0.0–2.1.1 (see the warning below) already forced those middleware into sync mode, while additionally breaking them.

Under ASGI, the middleware:

- Runs analyzers after the view returns, in the executor thread.
- Captures queries from `async def` views and from sync views alike.
- Captures queries issued inside `sync_to_async`-wrapped helpers — provided
  they use the default `thread_sensitive=True`. See
  [Mixed Sync/Async Code](#mixed-syncasync-code) for the `thread_sensitive=False`
  exception.

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

### Embedding the middleware around an async handler

Through Django's `MIDDLEWARE` chain the middleware always runs in sync mode (`async_capable = False`), so `__call__` routes every request to the synchronous path. There is a second, **supported** route for advanced users who embed the middleware by hand rather than listing it in `MIDDLEWARE`: constructing it directly around an async `get_response`.

```python
from query_doctor.middleware import QueryDoctorMiddleware

# get_response is an async callable (e.g. an ASGI handler or async view).
instrumented = QueryDoctorMiddleware(async_get_response)
response = await instrumented(request)   # native async path -> __acall__
```

When the wrapped `get_response` is a coroutine function, the middleware detects it at construction and `__call__` awaits `__acall__`, which runs the same capture-and-analyze pipeline without adapting through `sync_to_async`. This is the path `tests/test_async_support.py` and `tests/test_asgi_middleware_chain.py` exercise, and it is kept as a supported API precisely so those tests remain meaningful.

Two caveats apply on this route:

- **You own the thread placement.** Django is not adapting the middleware into its thread-sensitive executor here, so capture is correct only when the ORM work runs on the same thread as the `await` — see [The Context Manager in Async Code](#the-context-manager-in-async-code) for the same thread-locality constraint.
- **The analysis and the reporting both run inline on your loop.** `__acall__` calls `_analyze_and_report()` without awaiting it, so the analyzers *and* the reporters run on your event loop thread and block it for their combined duration. The **analysis stage** scales with the number of *captured queries*, roughly linearly; the measured figures are below. **They do not include reporter cost**, which is additional and unmeasured: it depends on which reporters you have configured, and a log line and a rendered HTML dashboard are not the same order of magnitude. Reporters run only when the request produced at least one prescription, so a clean request pays none of that — the expensive combination is a request that both issued many queries and has findings to report, which is exactly the case the tool exists to surface. One cost is not conditional on findings: with `ADMIN_DASHBOARD.enabled` set, the middleware records every report into the dashboard buffer inline, findings or not. The `MIDDLEWARE`-chain path does not have any of this property, because Django runs the whole middleware in the executor thread.


### Analysis cost on the hand-embed route

Regenerate this table with `python -m scripts.bench_analyze` — the harness prints the machine, the
Django version, the number of enabled analyzers, the number of `.queryignore` rules loaded, and the
shape of the workload, because all five change the answer.

| captured queries | distinct fingerprints | findings | median | p10 - p90 |
|---:|---:|---:|---:|---:|
| 0 | 0 | 0 | 0.14 ms | 0.13 - 0.14 |
| 1 | 1 | 1 | 0.25 ms | 0.24 - 0.25 |
| 10 | 2 | 3 | 0.91 ms | 0.89 - 0.93 |
| 50 | 3 | 6 | 3.68 ms | 3.65 - 3.75 |
| 100 | 4 | 8 | 6.46 ms | 6.38 - 7.05 |
| 500 | 16 | 32 | 32.00 ms | 31.57 - 32.63 |

Measured on one development machine (Python 3.12.0, Django 6.0.7, Windows), all 8 analyzers
enabled, 200 timed calls per row after 5 discarded warm-up calls, 0 `.queryignore` rules loaded.
The workload is 25% single-row writes and 75% wide `SELECT`s carrying a `WHERE` and an `ORDER BY`,
spread over one fingerprint per 25 captures.

`p10 - p90` is dispersion *within* one run, and it badly understates variation *between* runs. A
second run on this dedicated machine moved the medians by up to 7% (0.91 to 0.85 ms at 10 captures,
6.46 to 6.40 at 100, 32.00 to 31.73 at 500), some of it already outside the published band. On a
shared or virtualised host the swing is far larger: two runs of the same command on one such machine
measured 26.90 ms and 32.24 ms at 500 captures, **~20% apart**. So a run of yours that disagrees with
this table by tens of percent is telling you about your host, not about a defect. Take the shares
below, not the absolute milliseconds, as the durable result.

The 0-query row is the pipeline's floor, not this route's floor: `_analyze_and_report()` returns at
`middleware.py` before reaching the analysis pipeline when nothing was captured, so a request that
issued no queries costs `__acall__` config loading and the `_should_process()` check, not 0.14 ms of
analysis. That short-circuit is the middleware's alone — `diagnose_queries()`, the Celery
integration, the pytest plugin, `check_queries`, `fix_queries` and `diagnose_project` all call
`pipeline.analyze()` unguarded, and do pay the floor on an empty query list.

!!! note "Query count alone does not predict this"
    Cost is dominated by how much SQL each analyzer has to parse, not by how many queries there
    are. The default run prints a per-analyzer breakdown at the largest count: on the workload
    above the complexity analyzer alone is 22.34 ms of the 32.83 ms pipeline total, **68%**, with
    `missing_index` (15%) and `fat_select` (12%) next and the remaining five analyzers under 5%
    between them. The eight analyzers sum to 32.58 ms against that 32.83 ms total; the 0.26 ms gap
    is discovery dispatch and the one `load_queryignore()` call the pipeline makes per invocation,
    which no analyzer is responsible for. The breakdown times the pipeline again in its own loop,
    so its 32.83 ms and the table's 32.00 ms are two samples of the same thing rather than a
    contradiction — compare shares within the breakdown, not across the two.

    Replacing the wide `SELECT` with a single-column one, holding the count and the fingerprint
    spread fixed — `python -m scripts.bench_analyze --select-width narrow` — measured **3.2x
    cheaper at 100 captures (6.46 ms to 2.02 ms) and 3.5x cheaper at 500 (32.00 ms to 9.08 ms)**.
    The narrow workload also produces one finding fewer per row from 1 capture up, because
    `fat_select` has nothing to report on a one-column projection. The grouping analyzers are
    additionally O(distinct fingerprints) rather than O(queries), so 500 near-identical queries
    cost less than the table suggests and 500 distinct wide ones cost more.

    Treat the table as an order of magnitude for a deliberately unfavourable workload, and re-run
    the harness against your own if the number matters to you.

---

## Django Async ORM Methods

**Through the `MIDDLEWARE` chain**, Django's async ORM methods (`aget`, `acreate`, `acount`, `aexists`, async iteration) ultimately execute through the same database connection as their sync counterparts, so the interceptor's `execute_wrapper` captures them identically. Async iteration over querysets is captured the same way. Measured for all five on Django 6.0 and 4.2 by `tests/test_asgi_middleware_chain.py::TestASGIAsyncORMCapture`, which drives a real `ASGIHandler` and asserts the captured query *counts* plus a per-method SQL fragment — a raw `SELECT 1` cannot satisfy it.

!!! warning "Not on the hand-embedding route"

    Those same five methods capture **nothing** when the middleware is embedded by hand around an async handler, the route described under [Embedding the middleware around an async handler](#embedding-the-middleware-around-an-async-handler).

    `__acall__` installs the `execute_wrapper` on the event loop thread's connection, while every `a*` method is internally `sync_to_async(thread_sensitive=True)`, so the ORM runs on an executor thread holding a different `connections["default"]`. This is the thread-placement caveat on that route applied to async ORM calls, and the same cause as the `diagnose_queries()` limitation below. The behaviour is pinned by `tests/test_asgi_middleware_chain.py::TestDirectEmbedAsyncORMNotCaptured`, against a sync view doing identical ORM work through the same driver that captures 2 queries.

    **Since 2.3.0 it says so.** The behaviour is unchanged -- the route still captures nothing -- but it no longer does so silently. `__acall__` asks the thread-sensitive executor whether it can see the installed interceptor; when it cannot, a `QueryDoctorWarning` names the limitation and steers you to the `MIDDLEWARE` chain. An async handler doing sync ORM inline resolves the loop thread's own connection, finds the interceptor there, and does not warn.

    The warning reports a property of the **wiring**, not of one request, so a handler that touches no database at all also matches it, and it is emitted at most **once per middleware instance** rather than once per request. Suites that escalate warnings to errors will fail on a hand-embedded async middleware; see [`UPGRADING.md`](https://github.com/hassanzaibhay/django-query-doctor/blob/main/UPGRADING.md).

    Use the `MIDDLEWARE` chain to diagnose async ORM calls.

---

## The Context Manager in Async Code

!!! danger "`diagnose_queries()` captures nothing inside an `async def` function"

    Measured on Django 6.0 under a real ASGI handler: a `with diagnose_queries():` block inside an `async def` view reports **zero queries**, however many the block issues.

    **Since 2.2.0 it says so.** Entering the block from a coroutine emits a `QueryDoctorWarning` naming the limitation and steering you to the middleware. The behaviour is unchanged — the block still captures nothing — but it no longer does so silently. The predicate is whether an event loop is running on the entering thread, which fires only on this broken path: a `def` view served under ASGI and a `sync_to_async`-wrapped helper both run in the executor thread, capture correctly, and do not warn. Suites that escalate warnings to errors will fail on such a block; see [`UPGRADING.md`](https://github.com/hassanzaibhay/django-query-doctor/blob/main/UPGRADING.md).

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

> **Not supported:** `@diagnose` does not detect or await coroutine functions. Applied to an `async def` view, the wrapped call returns the coroutine object and the capture context exits before the view body runs, so nothing useful is captured. Both halves are pinned by `tests/test_decorators.py::TestDiagnoseOnCoroutineFunctions`: the decorator returns an un-awaited coroutine, and the attached report shows zero queries because it was finalized before the body ran.

For async views, use the middleware. A `with diagnose_queries():` block inside an `async def` view body does not work either -- see the warning above.

---

## Mixed Sync/Async Code

Django allows mixing sync and async code using `sync_to_async` and `async_to_sync`. Queries made in a `sync_to_async`-wrapped helper are captured **when the wrapper keeps the default `thread_sensitive=True`**, because the helper then runs in the same thread-sensitive executor the middleware itself was adapted into (see [How capture works under ASGI](#how-capture-works-under-asgi)), so it resolves to the same thread-local connection object the interceptor is installed on:

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

!!! warning "`thread_sensitive=False` is not captured"

    Passing `thread_sensitive=False` sends the helper to a general executor
    thread instead of the thread-sensitive one the middleware was adapted into.
    Django keeps connections in thread-local storage, so the helper resolves a
    *different* `connections["default"]` than the one the `execute_wrapper` is
    installed on, and its queries are never seen — the same cause as the
    hand-embedding limitation above.

    ```python
    # Captured -- default thread_sensitive=True
    await sync_to_async(get_related_books)(book)

    # NOT captured -- runs on a different thread, different connection
    await sync_to_async(get_related_books, thread_sensitive=False)(book)
    ```

    Measured both ways by
    `tests/test_asgi_middleware_chain.py::TestSyncToAsyncThreadSensitivity`,
    which asserts one query captured for the default and zero for
    `thread_sensitive=False`, and additionally asserts the thread and
    connection identities differ — so a passing result cannot come from a
    harness that captures nothing.

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
