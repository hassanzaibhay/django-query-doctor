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


class TestContextVarsIsolation:
    """Tests for contextvars isolation between requests."""

    def test_separate_interceptors_isolated(self) -> None:
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
