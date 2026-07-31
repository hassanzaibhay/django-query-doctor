"""Tests for async Django support.

Verifies that the middleware works with both sync and async views,
that contextvars-based state isolation works, and that the interceptor
correctly captures queries in async contexts.
"""

from __future__ import annotations

import asyncio

import pytest
from django.test import RequestFactory

from query_doctor.interceptor import QueryInterceptor
from query_doctor.middleware import QueryDoctorMiddleware


class TestInterceptorContextVars:
    """Tests that the interceptor uses contextvars for state storage."""

    def test_interceptor_captures_queries(self) -> None:
        """Interceptor should capture queries in sync context."""
        interceptor = QueryInterceptor(capture_stack=False)

        def mock_execute(sql: str, params: object, many: bool, context: dict) -> None:  # type: ignore[type-arg]
            return None

        interceptor(mock_execute, "SELECT 1", None, False, {})

        queries = interceptor.get_queries()
        assert len(queries) == 1
        assert "SELECT 1" in queries[0].sql

    def test_interceptor_clear(self) -> None:
        """clear() should reset the captured queries."""
        interceptor = QueryInterceptor(capture_stack=False)

        def mock_execute(sql: str, params: object, many: bool, context: dict) -> None:  # type: ignore[type-arg]
            return None

        interceptor(mock_execute, "SELECT 1", None, False, {})
        assert len(interceptor.get_queries()) == 1

        interceptor.clear()
        assert len(interceptor.get_queries()) == 0

    def test_multiple_queries_captured(self) -> None:
        """Multiple queries should all be captured."""
        interceptor = QueryInterceptor(capture_stack=False)

        def mock_execute(sql: str, params: object, many: bool, context: dict) -> None:  # type: ignore[type-arg]
            return None

        interceptor(mock_execute, "SELECT 1", None, False, {})
        interceptor(mock_execute, "SELECT 2", None, False, {})
        interceptor(mock_execute, "SELECT 3", None, False, {})

        assert len(interceptor.get_queries()) == 3


class TestMiddlewareAsyncCapable:
    """Tests for the middleware's capability declaration.

    Until 2.1.1 this asserted ``async_capable is True``. That is deliberately
    inverted -- do not "fix" it back. Declaring the middleware async-capable
    makes Django run it on the event loop thread, while Django runs all ORM work
    in a thread-sensitive executor thread. ``connections["default"]`` is
    thread-local (``django/db/utils.py`` sets ``thread_critical = True``), so the
    execute_wrapper ends up on a connection object the queries never touch and
    nothing is captured. Declaring it sync-only makes Django adapt it with
    ``sync_to_async(thread_sensitive=True)``, putting it in the same thread and
    on the same connection as the ORM. See tests/test_asgi_middleware_chain.py.
    """

    def test_sync_capable(self) -> None:
        """Middleware should be sync_capable."""
        assert getattr(QueryDoctorMiddleware, "sync_capable", True) is True

    def test_not_async_capable(self) -> None:
        """Middleware must declare async_capable = False so ASGI capture works."""
        assert QueryDoctorMiddleware.async_capable is False


class TestMiddlewareSyncPath:
    """Tests that the sync path still works correctly."""

    def test_sync_view_works(self) -> None:
        """Sync view should work through the middleware."""
        from django.http import HttpResponse

        def sync_view(request: object) -> HttpResponse:
            return HttpResponse("OK")

        middleware = QueryDoctorMiddleware(sync_view)
        factory = RequestFactory()
        request = factory.get("/test/")

        response = middleware(request)

        assert response.status_code == 200

    @pytest.mark.django_db
    def test_sync_view_captures_queries(self) -> None:
        """Sync view with DB queries should have queries captured."""
        from django.http import HttpResponse

        def sync_view(request: object) -> HttpResponse:
            from tests.testapp.models import Book

            list(Book.objects.all())
            return HttpResponse("OK")

        middleware = QueryDoctorMiddleware(sync_view)
        factory = RequestFactory()
        request = factory.get("/test/")

        response = middleware(request)

        assert response.status_code == 200


class TestMiddlewareAsyncPath:
    """Tests for async view handling."""

    @pytest.mark.django_db
    def test_async_view_works(self) -> None:
        """Async view should work through the middleware."""
        from django.http import HttpResponse

        async def async_view(request: object) -> HttpResponse:
            return HttpResponse("async OK")

        middleware = QueryDoctorMiddleware(async_view)
        factory = RequestFactory()
        request = factory.get("/test/")

        # The middleware should detect async and return a coroutine
        result = middleware(request)

        response = asyncio.run(result) if asyncio.iscoroutine(result) else result

        assert response.status_code == 200

    @pytest.mark.django_db
    def test_async_view_with_sync_db(self) -> None:
        """Async view using sync_to_async for DB should work."""
        from django.http import HttpResponse

        try:
            from asgiref.sync import sync_to_async
        except ImportError:
            pytest.skip("asgiref not installed")

        async def async_view(request: object) -> HttpResponse:
            get_books = sync_to_async(
                lambda: list(
                    __import__("tests.testapp.models", fromlist=["Book"]).Book.objects.all()
                )
            )
            await get_books()
            return HttpResponse("async DB OK")

        middleware = QueryDoctorMiddleware(async_view)
        factory = RequestFactory()
        request = factory.get("/test/")

        result = middleware(request)

        response = asyncio.run(result) if asyncio.iscoroutine(result) else result

        assert response.status_code == 200


class TestInterceptorInstanceSeparation:
    """Two interceptor instances do not share a query list.

    Named for what it actually establishes. This passes on instance
    separation alone -- a plain ``self._queries = []`` attribute would satisfy
    it -- so it is not evidence about contextvars, despite the storage being a
    ``ContextVar``. See docs/deep-dive/architecture.md, "What that test does
    and does not establish", for why no test here discriminates the two.
    """

    def test_separate_interceptors_have_separate_query_lists(self) -> None:
        """Two interceptor instances should have isolated query lists."""
        interceptor1 = QueryInterceptor(capture_stack=False)
        interceptor2 = QueryInterceptor(capture_stack=False)

        def mock_execute(sql: str, params: object, many: bool, context: dict) -> None:  # type: ignore[type-arg]
            return None

        interceptor1(mock_execute, "SELECT 1", None, False, {})
        interceptor2(mock_execute, "SELECT 2", None, False, {})

        assert len(interceptor1.get_queries()) == 1
        assert len(interceptor2.get_queries()) == 1
        assert interceptor1.get_queries()[0].sql == "SELECT 1"
        assert interceptor2.get_queries()[0].sql == "SELECT 2"


class TestDocumentedAsyncLimitationsAreBacked:
    """Entry 31: claims in async-support.md that nothing exercised.

    The inventory left these asserted-unbacked. Each is cheap to measure, and
    an asserted limitation that nobody runs is exactly the kind of claim that
    goes stale without anyone noticing.
    """

    def test_async_with_diagnose_queries_raises(self) -> None:
        """`async with diagnose_queries()` raises, and the type is version-dependent.

        CPython 3.11 gave the async-protocol failure a dedicated `TypeError`
        ("does not support the asynchronous context manager protocol"). On
        3.10 the same code raises `AttributeError: __aenter__` from the
        missing attribute lookup. Both are asserted, because the guide
        documents this for every supported interpreter and a reader on 3.10
        writing `except TypeError` would not catch it.
        """
        import asyncio
        import sys

        from query_doctor.context_managers import diagnose_queries

        async def use_it() -> None:
            async with diagnose_queries():
                pass

        with pytest.raises((TypeError, AttributeError)) as excinfo:
            asyncio.run(use_it())

        if sys.version_info >= (3, 11):
            assert isinstance(excinfo.value, TypeError)
            assert "asynchronous context manager" in str(excinfo.value)
        else:
            assert isinstance(excinfo.value, AttributeError)
            assert "__aenter__" in str(excinfo.value)

    def test_diagnose_queries_works_synchronously(self) -> None:
        """Positive control: the same manager is fine outside a coroutine."""
        from query_doctor.context_managers import diagnose_queries

        with diagnose_queries() as report:
            pass
        assert report.total_queries == 0

    @pytest.mark.django_db
    def test_query_budget_on_a_coroutine_does_not_enforce(self) -> None:
        """`@query_budget` on an `async def` is documented as unsupported.

        The decorator's wrapper is synchronous, so calling the coroutine
        function returns the coroutine object and the budget check runs
        against zero captured queries -- it cannot raise however many queries
        the body goes on to issue.
        """
        import asyncio

        from query_doctor.decorators import query_budget
        from tests.factories import BookFactory
        from tests.testapp.models import Book

        BookFactory.create_batch(4)

        @query_budget(max_queries=0)
        async def over_budget() -> int:
            return len([b.author.name for b in Book.objects.all()])

        # No QueryBudgetError, because the body has not run yet.
        coro = over_budget()
        assert asyncio.iscoroutine(coro)
        coro.close()

    @pytest.mark.django_db
    def test_query_budget_on_a_sync_function_does_enforce(self) -> None:
        """Negative control: the decorator is not simply broken."""
        from query_doctor.decorators import query_budget
        from query_doctor.exceptions import QueryBudgetError
        from tests.factories import BookFactory
        from tests.testapp.models import Book

        BookFactory.create_batch(4)

        @query_budget(max_queries=0)
        def over_budget() -> int:
            return len([b.author.name for b in Book.objects.all()])

        with pytest.raises(QueryBudgetError):
            over_budget()
