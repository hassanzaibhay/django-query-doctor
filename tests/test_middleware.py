"""Tests for Django middleware in query_doctor.middleware."""

from __future__ import annotations

import pytest
from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory, override_settings

from query_doctor.middleware import QueryDoctorMiddleware
from tests.factories import BookFactory


def _dummy_view(request: HttpRequest) -> HttpResponse:
    """Simple view that returns 200."""
    return HttpResponse("OK")


def _nplusone_view(request: HttpRequest) -> HttpResponse:
    """View that triggers N+1 queries."""
    from tests.testapp.models import Book

    for book in Book.objects.all():
        _ = book.author.name
    return HttpResponse("OK")


@pytest.mark.django_db
class TestQueryDoctorMiddleware:
    """Tests for QueryDoctorMiddleware."""

    def test_basic_request_passes_through(self) -> None:
        """Middleware should not interfere with normal requests."""
        middleware = QueryDoctorMiddleware(_dummy_view)
        factory = RequestFactory()
        request = factory.get("/")
        response = middleware(request)
        assert response.status_code == 200

    def test_response_content_unchanged(self) -> None:
        """Middleware should not alter response content."""
        middleware = QueryDoctorMiddleware(_dummy_view)
        factory = RequestFactory()
        request = factory.get("/")
        response = middleware(request)
        assert response.content == b"OK"

    def test_detects_nplusone_in_request(self) -> None:
        """Middleware should detect N+1 queries during a request."""
        for _ in range(5):
            BookFactory()

        middleware = QueryDoctorMiddleware(_nplusone_view)
        factory = RequestFactory()
        request = factory.get("/books/")
        # Should not crash even when N+1 is detected
        response = middleware(request)
        assert response.status_code == 200

    @override_settings(QUERY_DOCTOR={"ENABLED": False})
    def test_disabled_skips_analysis(self) -> None:
        """When disabled, middleware should skip analysis."""
        from query_doctor.conf import get_config

        get_config.cache_clear()

        middleware = QueryDoctorMiddleware(_dummy_view)
        factory = RequestFactory()
        request = factory.get("/")
        response = middleware(request)
        assert response.status_code == 200

        get_config.cache_clear()

    @override_settings(QUERY_DOCTOR={"IGNORE_URLS": ["/health/"]})
    def test_ignore_urls(self) -> None:
        """Requests matching IGNORE_URLS should skip analysis."""
        from query_doctor.conf import get_config

        get_config.cache_clear()

        middleware = QueryDoctorMiddleware(_dummy_view)
        factory = RequestFactory()
        request = factory.get("/health/")
        response = middleware(request)
        assert response.status_code == 200

        get_config.cache_clear()

    def test_never_crashes_on_error(self) -> None:
        """Middleware should never crash the host app."""
        middleware = QueryDoctorMiddleware(_dummy_view)
        factory = RequestFactory()
        request = factory.get("/")
        # Even if something goes wrong internally, the request should succeed
        response = middleware(request)
        assert response.status_code == 200

    def test_view_exception_propagates(self) -> None:
        """If the view raises, the exception should propagate normally."""

        def error_view(request: HttpRequest) -> HttpResponse:
            raise ValueError("View error")

        middleware = QueryDoctorMiddleware(error_view)
        factory = RequestFactory()
        request = factory.get("/")

        with pytest.raises(ValueError, match="View error"):
            middleware(request)
