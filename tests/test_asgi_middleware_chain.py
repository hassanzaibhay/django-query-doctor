"""Tests for QueryDoctorMiddleware under Django's real ASGI handler.

Regression coverage for issue #11 and for the zero-capture defect it exposed.

Two separate failures were measured on 2.1.1:

1. The middleware declared ``async_capable = True`` without marking its instance
   as a coroutine function, so Django wrapped it synchronously while having
   already recorded the handler as async. Every middleware listed before it in
   ``MIDDLEWARE`` then degraded to sync mode and was handed an un-awaited
   coroutine, which three of Django's seven startproject defaults raise on.
2. In the configurations that did not crash, the middleware ran on the event
   loop thread while Django ran all ORM work in a thread-sensitive executor
   thread. ``connections["default"]`` is thread-local
   (``django/db/utils.py`` sets ``thread_critical = True``), so the
   ``execute_wrapper`` the middleware installed was on a different connection
   object than the one the ORM used, and nothing was ever captured.

Declaring ``async_capable = False`` fixes both: Django adapts the middleware
into the same thread-sensitive executor the ORM uses, so the wrapper and the
queries share a connection.

These tests drive a real ``ASGIHandler`` (see ``tests/asgi_driver.py``).
``django.test.AsyncClient`` is deliberately not used for the chain assertions --
it bypasses the per-request ``ThreadSensitiveContext`` that decides the outcome.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from asgiref.sync import sync_to_async
from django.http import HttpResponse
from django.test import AsyncClient, Client, RequestFactory, override_settings

from query_doctor.interceptor import QueryInterceptor
from query_doctor.middleware import QueryDoctorMiddleware
from tests.asgi_driver import asgi_get_concurrent_sync, asgi_get_sync
from tests.testapp import views

QD = "query_doctor.middleware.QueryDoctorMiddleware"

# django/conf/project_template/project_name/settings.py-tpl, verbatim.
STARTPROJECT_DEFAULTS = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Defaults whose process_response touches the response object unconditionally,
# so on 2.1.1 they raised on the un-awaited coroutine.
RESPONSE_TOUCHING_STACKS = [
    pytest.param(["django.middleware.security.SecurityMiddleware", QD], id="security"),
    pytest.param(["django.middleware.common.CommonMiddleware", QD], id="common"),
    pytest.param(
        ["django.middleware.clickjacking.XFrameOptionsMiddleware", QD], id="clickjacking"
    ),
]

# Defaults that leave the response untouched on an ordinary GET. These returned
# 200 on 2.1.1 as well -- but captured nothing, which is why every case here
# asserts the query count and not just the status.
PASS_THROUGH_STACKS = [
    pytest.param(["django.contrib.sessions.middleware.SessionMiddleware", QD], id="session"),
    pytest.param(["django.middleware.csrf.CsrfViewMiddleware", QD], id="csrf"),
    pytest.param(
        [
            "django.contrib.sessions.middleware.SessionMiddleware",
            "django.contrib.auth.middleware.AuthenticationMiddleware",
            QD,
        ],
        id="session-auth",
    ),
    pytest.param(
        [
            "django.contrib.sessions.middleware.SessionMiddleware",
            "django.contrib.messages.middleware.MessageMiddleware",
            QD,
        ],
        id="session-messages",
    ),
]


class AnalysisSpy:
    """Records each ``_analyze_and_report`` call: query count, thread, connection."""

    def __init__(self) -> None:
        self.query_counts: list[int] = []
        self.thread: int | None = None
        self.connection_id: int | None = None

    @property
    def call_count(self) -> int:
        """Number of times the analysis stage ran."""
        return len(self.query_counts)

    @property
    def queries(self) -> int:
        """Query count seen by the single analysis call."""
        assert self.call_count == 1, f"expected exactly one analysis call, got {self.call_count}"
        return self.query_counts[0]


@pytest.fixture
def analysis_spy(monkeypatch: pytest.MonkeyPatch) -> AnalysisSpy:
    """Record what the analysis stage saw, and where it ran."""
    import threading

    from django.db import connections

    spy = AnalysisSpy()

    def _spy(
        self: QueryDoctorMiddleware,
        interceptor: QueryInterceptor,
        config: dict[str, Any],
        request: Any = None,
    ) -> None:
        spy.query_counts.append(len(interceptor.get_queries()))
        spy.thread = threading.get_ident()
        spy.connection_id = id(connections["default"])

    monkeypatch.setattr(QueryDoctorMiddleware, "_analyze_and_report", _spy)
    views.view_execution_record.clear()
    return spy


class TestASGIChainServesRequests:
    """The middleware must not break Django's async chain (issue #11)."""

    @pytest.mark.django_db
    @pytest.mark.parametrize("debug", [False, True])
    def test_documented_middleware_stack(self, analysis_spy: AnalysisSpy, debug: bool) -> None:
        """The stack from docs/guides/middleware.md must serve ASGI requests and capture."""
        stack = [*STARTPROJECT_DEFAULTS, QD]

        with override_settings(MIDDLEWARE=stack, DEBUG=debug):
            status, body = asgi_get_sync("/async/probe/")

        assert status == 200
        assert body == b"async ok"
        assert analysis_spy.queries == 1

    @pytest.mark.django_db
    @pytest.mark.parametrize("debug", [False, True])
    def test_middleware_placed_mid_stack(self, analysis_spy: AnalysisSpy, debug: bool) -> None:
        """Placement between Django's defaults must work too."""
        stack = [*STARTPROJECT_DEFAULTS[:3], QD, *STARTPROJECT_DEFAULTS[3:]]

        with override_settings(MIDDLEWARE=stack, DEBUG=debug):
            status, body = asgi_get_sync("/async/probe/")

        assert status == 200
        assert body == b"async ok"
        assert analysis_spy.queries == 1

    @pytest.mark.django_db
    @pytest.mark.parametrize("stack", RESPONSE_TOUCHING_STACKS)
    def test_response_touching_middleware_above(
        self, analysis_spy: AnalysisSpy, stack: list[str]
    ) -> None:
        """Any one response-touching middleware above ours broke the chain on 2.1.1."""
        with override_settings(MIDDLEWARE=stack):
            status, body = asgi_get_sync("/async/probe/")

        assert status == 200
        assert body == b"async ok"
        assert analysis_spy.queries == 1

    @pytest.mark.django_db
    @pytest.mark.parametrize("stack", PASS_THROUGH_STACKS)
    def test_pass_through_middleware_above(
        self, analysis_spy: AnalysisSpy, stack: list[str]
    ) -> None:
        """Stacks that never crashed still captured nothing on 2.1.1."""
        with override_settings(MIDDLEWARE=stack):
            status, body = asgi_get_sync("/async/probe/")

        assert status == 200
        assert body == b"async ok"
        assert analysis_spy.queries == 1

    @pytest.mark.django_db
    def test_middleware_alone(self, analysis_spy: AnalysisSpy) -> None:
        """A single-entry stack must serve requests and capture."""
        with override_settings(MIDDLEWARE=[QD]):
            status, body = asgi_get_sync("/async/probe/")

        assert status == 200
        assert body == b"async ok"
        assert analysis_spy.queries == 1


class TestASGICapture:
    """Capture must work for both view flavours, for the reason it works."""

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        ("path", "expected_body"),
        [("/sync/probe/", b"sync ok"), ("/async/probe/", b"async ok")],
    )
    def test_both_view_flavours_captured(
        self, analysis_spy: AnalysisSpy, path: str, expected_body: bytes
    ) -> None:
        """Sync and async views must both have their queries captured under ASGI."""
        with override_settings(MIDDLEWARE=[*STARTPROJECT_DEFAULTS, QD]):
            status, body = asgi_get_sync(path)

        assert status == 200
        assert body == expected_body
        assert analysis_spy.queries == 1

    @pytest.mark.django_db
    def test_middleware_and_view_share_thread_and_connection(
        self, analysis_spy: AnalysisSpy
    ) -> None:
        """Django must adapt the middleware into the executor the ORM runs on.

        This is the mechanism the capture depends on. ``connections["default"]``
        is thread-local, so if the middleware ran on the event loop thread while
        the ORM ran in the thread-sensitive executor, the execute_wrapper would
        be installed on a connection object the queries never touch -- which is
        what shipped in 2.1.1.
        """
        with override_settings(MIDDLEWARE=[*STARTPROJECT_DEFAULTS, QD]):
            status, _ = asgi_get_sync("/async/probe/")

        assert status == 200
        assert views.view_execution_record["thread"] == analysis_spy.thread
        assert views.view_execution_record["connection"] == analysis_spy.connection_id

    @pytest.mark.django_db
    def test_interceptor_is_installed_on_the_connection_the_view_uses(
        self, analysis_spy: AnalysisSpy
    ) -> None:
        """The view's connection must carry the middleware's execute_wrapper."""
        with override_settings(MIDDLEWARE=[*STARTPROJECT_DEFAULTS, QD]):
            asgi_get_sync("/async/probe/")

        assert views.view_execution_record["wrappers"] == 1


class TestConcurrentRequestIsolation:
    """Concurrent ASGI requests must not see each other's queries."""

    @pytest.mark.django_db
    def test_each_report_holds_only_its_own_queries(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Ten interleaved requests, each asking for a different query count.

        Backs the claim in docs/deep-dive/architecture.md that concurrent ASGI
        requests do not interfere with each other. A report holding the wrong
        count proves queries leaked across requests; asserting only the status
        code would prove nothing.
        """
        seen: dict[str, int] = {}

        def _spy(
            self: QueryDoctorMiddleware,
            interceptor: QueryInterceptor,
            config: dict[str, Any],
            request: Any = None,
        ) -> None:
            seen[request.path] = len(interceptor.get_queries())

        monkeypatch.setattr(QueryDoctorMiddleware, "_analyze_and_report", _spy)

        counts = range(1, 11)
        paths = [f"/async/burst/{n}/" for n in counts]

        with override_settings(MIDDLEWARE=[*STARTPROJECT_DEFAULTS, QD]):
            results = asgi_get_concurrent_sync(paths)

        assert [status for status, _ in results] == [200] * len(paths)
        assert seen == {f"/async/burst/{n}/": n for n in counts}


class TestWSGIUnaffected:
    """The sync path must keep working exactly as before."""

    @pytest.mark.django_db
    def test_wsgi_request_captures_queries(self, analysis_spy: AnalysisSpy) -> None:
        """Same stack under WSGI must still capture the view's query."""
        with override_settings(MIDDLEWARE=[*STARTPROJECT_DEFAULTS, QD]):
            response = Client().get("/sync/probe/")

        assert response.status_code == 200
        assert analysis_spy.queries == 1


class TestAsyncClientCapture:
    """Supplementary: users writing async tests reach for django.test.AsyncClient.

    AsyncClient does not open a per-request ThreadSensitiveContext, so it is not
    the path this defect lives on -- but users will judge the package by what
    they see there, so the behaviour is pinned.
    """

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        ("path", "expected_body"),
        [("/sync/probe/", b"sync ok"), ("/async/probe/", b"async ok")],
    )
    def test_async_client_captures_queries(
        self, analysis_spy: AnalysisSpy, path: str, expected_body: bytes
    ) -> None:
        """Queries must be captured under AsyncClient as well."""
        with override_settings(MIDDLEWARE=[*STARTPROJECT_DEFAULTS, QD]):
            response = asyncio.run(AsyncClient().get(path))

        assert response.status_code == 200
        assert response.content == expected_body
        assert analysis_spy.queries == 1


class TestDirectInstantiationPredicate:
    """The middleware must use asgiref's coroutine predicate, not inspect's.

    ``inspect.iscoroutinefunction`` does not recognise asgiref-wrapped callables
    on Python 3.10 and 3.11 (``inspect.markcoroutinefunction`` arrived in 3.12).
    A middleware constructed directly around one then takes the sync path and
    runs the analysis stage before the view body instead of after it, so the
    report is always empty.
    """

    def test_analysis_runs_after_the_view_body(self) -> None:
        """Analyzers must run after the wrapped handler, not before it."""
        events: list[str] = []

        def view(request: Any) -> HttpResponse:
            events.append("view")
            return HttpResponse("ok")

        def _spy(
            self: QueryDoctorMiddleware,
            interceptor: QueryInterceptor,
            config: dict[str, Any],
            request: Any = None,
        ) -> None:
            events.append("analyze")

        original = QueryDoctorMiddleware._analyze_and_report
        QueryDoctorMiddleware._analyze_and_report = _spy  # type: ignore[method-assign]
        try:
            middleware = QueryDoctorMiddleware(sync_to_async(view))
            result = middleware(RequestFactory().get("/async/ok/"))
            if asyncio.iscoroutine(result):
                asyncio.run(result)
        finally:
            QueryDoctorMiddleware._analyze_and_report = original  # type: ignore[method-assign]

        assert events == ["view", "analyze"]

    def test_asgiref_wrapped_handler_detected_as_async(self) -> None:
        """An asgiref-wrapped handler must put the middleware on the async path."""

        def view(request: Any) -> HttpResponse:
            return HttpResponse("ok")

        middleware = QueryDoctorMiddleware(sync_to_async(view))

        assert middleware._is_async is True
