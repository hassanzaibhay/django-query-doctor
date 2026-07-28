"""Test views that trigger query patterns for integration testing."""

from __future__ import annotations

import asyncio
import threading

from asgiref.sync import sync_to_async
from django.db import connection, connections
from django.http import HttpResponse, JsonResponse

from tests.testapp.models import Book, Publisher

# Filled in by the probe views below so ASGI tests can compare the thread and
# connection the view ran on against the ones the middleware ran on.
view_execution_record: dict[str, object] = {}


def book_list_nplusone(request):
    """View that triggers N+1 queries by accessing author on each book."""
    books = []
    for book in Book.objects.all():
        books.append({"title": book.title, "author": book.author.name})
    return JsonResponse({"books": books})


def book_list_duplicate(request):
    """View that triggers duplicate queries by repeating the same query."""
    first = list(Book.objects.all().values_list("title", flat=True))
    second = list(Book.objects.all().values_list("title", flat=True))
    return JsonResponse({"first": first, "second": second})


def book_list_optimized(request):
    """View with optimized queries using select_related."""
    books = []
    for book in Book.objects.select_related("author").all():
        books.append({"title": book.title, "author": book.author.name})
    return JsonResponse({"books": books})


def book_list_missing_index(request):
    """View that filters on a non-indexed column to trigger missing_index."""
    books = list(Book.objects.filter(published_date="2024-01-01").values_list("title", flat=True))
    return JsonResponse({"books": books})


async def async_ok(request):
    """Async view with no database access, for exercising the ASGI middleware chain."""
    return HttpResponse("async ok")


def _run_one_query():
    """Issue one query and record the thread and connection it ran on."""
    view_execution_record["thread"] = threading.get_ident()
    view_execution_record["connection"] = id(connections["default"])
    view_execution_record["wrappers"] = len(connections["default"].execute_wrappers)
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")


def sync_probe(request):
    """Sync view issuing one query, for capture assertions."""
    _run_one_query()
    return HttpResponse("sync ok")


async def async_probe(request):
    """Async view issuing one query via sync_to_async, for capture assertions."""
    await sync_to_async(_run_one_query)()
    return HttpResponse("async ok")


async def async_probe_thread_insensitive(request):
    """Async view issuing one query via ``sync_to_async(thread_sensitive=False)``.

    The non-default half of the sync_to_async story. ``thread_sensitive=True``
    (the default, used by ``async_probe`` above) routes the helper into the same
    thread-sensitive executor the middleware was adapted into. Passing False
    sends it to a general executor thread instead, which resolves to a different
    thread-local ``connections["default"]``.
    """
    await sync_to_async(_run_one_query, thread_sensitive=False)()
    return HttpResponse("async ok")


# Async ORM probe views. Each issues its queries through Django's async ORM API
# and creates the rows it needs inside the same request, so every statement is
# issued on whichever connection that request's ORM work resolves to. Publisher
# is used because it has no required FK, so each async ORM call maps to exactly
# one query and the asserted counts stay readable.


async def async_orm_acreate(request):
    """Async view issuing one query via ``acreate``."""
    await Publisher.objects.acreate(name="Async Press", country="PK")
    return HttpResponse("acreate ok")


async def async_orm_aget(request):
    """Async view issuing one ``acreate`` then one ``aget``."""
    await Publisher.objects.acreate(name="Async Press", country="PK")
    await Publisher.objects.aget(name="Async Press")
    return HttpResponse("aget ok")


async def async_orm_acount(request):
    """Async view issuing one ``acreate`` then one ``acount``."""
    await Publisher.objects.acreate(name="Async Press", country="PK")
    await Publisher.objects.acount()
    return HttpResponse("acount ok")


async def async_orm_aexists(request):
    """Async view issuing one ``acreate`` then one ``aexists``."""
    await Publisher.objects.acreate(name="Async Press", country="PK")
    await Publisher.objects.filter(name="Async Press").aexists()
    return HttpResponse("aexists ok")


async def async_orm_aiter(request):
    """Async view issuing one ``acreate`` then one async iteration."""
    await Publisher.objects.acreate(name="Async Press", country="PK")
    _ = [publisher async for publisher in Publisher.objects.all()]
    return HttpResponse("aiter ok")


def sync_orm_publisher(request):
    """Sync view issuing the same two Publisher queries as ``async_orm_aiter``.

    Not routed: it exists to be embedded directly, as the positive control for
    the hand-embedding assertions. Holding the ORM work identical and varying
    only sync-versus-async makes the route the single variable under test.
    """
    Publisher.objects.create(name="Async Press", country="PK")
    _ = list(Publisher.objects.all())
    return HttpResponse("sync orm ok")


def _run_n_queries(count):
    """Issue ``count`` queries."""
    with connection.cursor() as cursor:
        for _ in range(count):
            cursor.execute("SELECT 1")


async def query_burst(request, count):
    """Async view issuing ``count`` queries, with awaits around them.

    Used to check capture isolation between concurrent ASGI requests: each
    request asks for a different count, so a report holding the wrong number
    proves queries leaked between requests. The sleeps force the requests to
    interleave rather than run to completion one at a time.
    """
    await asyncio.sleep(0.05)
    await sync_to_async(_run_n_queries)(count)
    await asyncio.sleep(0.05)
    return HttpResponse(f"burst {count}")
