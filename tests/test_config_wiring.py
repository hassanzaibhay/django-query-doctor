"""Tests that documented config keys actually reach the code they configure.

Each test here pins a settings key to the behaviour it claims to control. The
keys covered were present in ``DEFAULT_CONFIG`` but read by no code path
(FOLLOWUPS.md entries 2 and 3), so the failure mode these guard against is a
setting that is accepted, documented, and silently ignored.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory, override_settings

from query_doctor import QueryDoctorWarning
from query_doctor.conf import get_config


def _nplusone_view(request: HttpRequest) -> HttpResponse:
    """View that issues queries, so the interceptor captures callsites."""
    from tests.testapp.models import Book

    for book in Book.objects.all():
        _ = book.author.name
    return HttpResponse("OK")


@pytest.mark.django_db
class TestStackTraceExclude:
    """STACK_TRACE_EXCLUDE must reach capture_callsite()."""

    @override_settings(
        QUERY_DOCTOR={"CAPTURE_STACK_TRACES": True, "STACK_TRACE_EXCLUDE": ["my_vendor_pkg"]}
    )
    def test_exclude_list_reaches_capture_callsite(self, monkeypatch: Any) -> None:
        """The configured exclude list must be passed through on every capture."""
        from query_doctor import interceptor as interceptor_module
        from query_doctor.middleware import QueryDoctorMiddleware
        from tests.factories import BookFactory

        BookFactory()

        seen: list[list[str] | None] = []
        real = interceptor_module.capture_callsite

        def _spy(exclude_modules: list[str] | None = None) -> Any:
            seen.append(exclude_modules)
            return real(exclude_modules)

        monkeypatch.setattr(interceptor_module, "capture_callsite", _spy)

        get_config.cache_clear()
        try:
            middleware = QueryDoctorMiddleware(_nplusone_view)
            middleware(RequestFactory().get("/"))
        finally:
            get_config.cache_clear()

        assert seen, "capture_callsite was never called; the test proves nothing"
        assert all(call == ["my_vendor_pkg"] for call in seen), (
            f"STACK_TRACE_EXCLUDE did not reach capture_callsite: {seen!r}"
        )


class TestQueryignorePath:
    """QUERYIGNORE_PATH must select the .queryignore file that is loaded."""

    def test_configured_path_is_loaded(self, tmp_path: Path) -> None:
        """A configured path must win over project-root discovery."""
        from query_doctor.ignore import load_queryignore

        ignore_file = tmp_path / "custom.queryignore"
        ignore_file.write_text("sql:SELECT * FROM legacy%\n", encoding="utf-8")

        with override_settings(QUERY_DOCTOR={"QUERYIGNORE_PATH": str(ignore_file)}):
            get_config.cache_clear()
            try:
                rules = load_queryignore()
            finally:
                get_config.cache_clear()

        assert [(r.rule_type, r.pattern) for r in rules] == [("sql", "SELECT * FROM legacy%")]

    def test_explicit_argument_still_wins(self, tmp_path: Path) -> None:
        """An explicit project_root must override the setting, not the reverse."""
        from query_doctor.ignore import load_queryignore

        configured = tmp_path / "configured.queryignore"
        configured.write_text("sql:FROM configured%\n", encoding="utf-8")
        explicit_root = tmp_path / "explicit"
        explicit_root.mkdir()
        (explicit_root / ".queryignore").write_text("sql:FROM explicit%\n", encoding="utf-8")

        with override_settings(QUERY_DOCTOR={"QUERYIGNORE_PATH": str(configured)}):
            get_config.cache_clear()
            try:
                rules = load_queryignore(explicit_root)
            finally:
                get_config.cache_clear()

        assert [r.pattern for r in rules] == ["FROM explicit%"]

    def test_unresolvable_path_warns_and_falls_back(self, tmp_path: Path) -> None:
        """A configured path that does not exist must warn, not degrade silently.

        Silently ignoring it is indistinguishable from never setting it, which
        is the exact failure the QueryDoctorWarning category exists to end.
        """
        from query_doctor.ignore import load_queryignore

        missing = tmp_path / "nope" / ".queryignore"

        with override_settings(QUERY_DOCTOR={"QUERYIGNORE_PATH": str(missing)}):
            get_config.cache_clear()
            try:
                with pytest.warns(QueryDoctorWarning) as record:
                    rules = load_queryignore()
            finally:
                get_config.cache_clear()

        assert rules == []
        message = str(record[0].message)
        assert "QUERYIGNORE_PATH" in message
        assert str(missing) in message


class TestAdminDashboardMaxReports:
    """ADMIN_DASHBOARD.max_reports must size the report ring buffer."""

    def test_max_reports_sizes_the_buffer(self) -> None:
        """The buffer must evict at the configured size, not the hardcoded 50."""
        from query_doctor import admin_panel
        from query_doctor.types import DiagnosisReport

        with override_settings(QUERY_DOCTOR={"ADMIN_DASHBOARD": {"max_reports": 3}}):
            get_config.cache_clear()
            admin_panel._report_buffer = None
            try:
                for i in range(10):
                    admin_panel.record_report(f"/path/{i}/", "GET", DiagnosisReport())
                buffer = admin_panel._get_buffer()
                assert len(buffer) == 3
                assert buffer[0]["path"] == "/path/7/"
            finally:
                admin_panel._report_buffer = None
                get_config.cache_clear()


class TestUnknownReporterNames:
    """An unrecognised REPORTERS name must warn instead of doing nothing."""

    def test_unknown_name_warns(self) -> None:
        """A name the dispatch does not recognise is silently discarded today."""
        from query_doctor.middleware import _get_reporters

        with pytest.warns(QueryDoctorWarning) as record:
            reporters = _get_reporters({"REPORTERS": ["console", "consoel"]})

        assert len(reporters) == 1
        message = str(record[0].message)
        assert "consoel" in message
        assert "console" in message

    def test_reporter_classes_not_wired_are_named_in_the_warning(self) -> None:
        """`html`/`otel` are real classes reached by direct invocation, not by name.

        Naming them specifically is the difference between "you typed it wrong"
        and "that reporter exists but is not dispatched here".
        """
        from query_doctor.middleware import _get_reporters

        with pytest.warns(QueryDoctorWarning) as record:
            _get_reporters({"REPORTERS": ["otel"]})

        message = str(record[0].message)
        assert "otel" in message
        assert "OTelReporter" in message

    def test_recognised_names_do_not_warn(self) -> None:
        """Positive control: the supported names must stay silent."""
        import warnings

        from query_doctor.middleware import _get_reporters

        with warnings.catch_warnings():
            warnings.simplefilter("error", QueryDoctorWarning)
            reporters = _get_reporters({"REPORTERS": ["console", "json", "log"]})

        assert len(reporters) == 3


from query_doctor.stack_tracer import capture_callsite as _real_capture  # noqa: E402


def _spy_factory(seen: list[Any]) -> Any:
    """A capture_callsite replacement that records every call, then delegates."""

    def _spy(exclude_modules: list[str] | None = None) -> Any:
        seen.append(exclude_modules)
        return _real_capture(exclude_modules)

    return _spy


def _drive_context_manager() -> None:
    from query_doctor.context_managers import diagnose_queries
    from tests.factories import BookFactory
    from tests.testapp.models import Book

    BookFactory()
    with diagnose_queries():
        list(Book.objects.all())


def _drive_check_queries() -> None:
    from io import StringIO

    from django.core.management import call_command

    from tests.factories import BookFactory

    for _ in range(3):
        BookFactory()
    call_command(
        "check_queries", "--url", "/books/nplusone/", "--format", "json", stdout=StringIO()
    )


def _drive_fix_queries() -> None:
    from io import StringIO

    from django.core.management import call_command

    from tests.factories import BookFactory

    for _ in range(3):
        BookFactory()
    call_command("fix_queries", "--url", "/books/nplusone/", "--dry-run", stdout=StringIO())


def _drive_query_budget() -> None:
    from io import StringIO

    from django.core.management import call_command

    from tests.factories import BookFactory

    BookFactory()
    call_command(
        "query_budget",
        "--max-queries",
        "100000",
        "--execute",
        "from tests.testapp.models import Book\nlist(Book.objects.all())",
        stdout=StringIO(),
    )


def _drive_project_diagnoser() -> None:
    from query_doctor.project_diagnoser import ProjectDiagnoser
    from query_doctor.url_discovery import DiscoveredURL
    from tests.factories import BookFactory

    for _ in range(3):
        BookFactory()
    url = DiscoveredURL(
        pattern="/books/nplusone/",
        name=None,
        app_name="testapp",
        view_name="book_list_nplusone",
        methods=["GET"],
        has_parameters=False,
    )
    ProjectDiagnoser().diagnose([url])


def _drive_celery() -> None:
    from query_doctor.celery_integration import diagnose_task
    from tests.factories import BookFactory
    from tests.testapp.models import Book

    @diagnose_task()
    def _task() -> str:
        BookFactory()
        list(Book.objects.all())
        return "done"

    _task()


def _drive_pytest_plugin() -> None:
    import warnings as _warnings

    from query_doctor.pytest_plugin import query_doctor as _qd_fixture
    from tests.factories import BookFactory
    from tests.testapp.models import Book

    raw = _qd_fixture.__wrapped__  # type: ignore[attr-defined]
    BookFactory()

    finalizers: list[Any] = []

    class _FakeNode:
        nodeid = "tests/test_config_wiring.py::_drive_pytest_plugin"

    class _FakeRequest:
        node = _FakeNode()

        def addfinalizer(self, func: Any) -> None:
            finalizers.append(func)

    with _warnings.catch_warnings():
        _warnings.simplefilter("ignore", QueryDoctorWarning)
        raw(_FakeRequest())
        list(Book.objects.all())
        for func in finalizers:
            func()


@pytest.mark.django_db
class TestCaptureStackTraces:
    """CAPTURE_STACK_TRACES=False must be honoured at every interceptor site.

    Today only the two middleware sites read the setting; the seven other
    construction sites hardcode ``QueryInterceptor()`` (capture_stack defaults
    to True) and capture stack traces regardless. The observable is
    capture_callsite: with the setting False it must never be called; the
    True run is the paired positive control proving the driver reaches capture.
    """

    def _check(self, driver: Any, monkeypatch: Any) -> None:
        import query_doctor.interceptor as interceptor_module

        seen_false: list[Any] = []
        monkeypatch.setattr(interceptor_module, "capture_callsite", _spy_factory(seen_false))
        self._drive(driver, capture=False)
        assert seen_false == [], (
            f"CAPTURE_STACK_TRACES=False ignored: "
            f"capture_callsite was called {len(seen_false)} time(s)"
        )

        seen_true: list[Any] = []
        monkeypatch.setattr(interceptor_module, "capture_callsite", _spy_factory(seen_true))
        self._drive(driver, capture=True)
        assert seen_true, (
            "positive control failed: capture_callsite was never called with "
            "CAPTURE_STACK_TRACES=True, so the False assertion proves nothing"
        )

    @staticmethod
    def _drive(driver: Any, capture: bool) -> None:
        get_config.cache_clear()
        try:
            with override_settings(QUERY_DOCTOR={"CAPTURE_STACK_TRACES": capture}):
                get_config.cache_clear()
                driver()
        finally:
            get_config.cache_clear()

    def test_context_manager_site(self, monkeypatch: Any) -> None:
        self._check(_drive_context_manager, monkeypatch)

    def test_check_queries_site(self, monkeypatch: Any) -> None:
        self._check(_drive_check_queries, monkeypatch)

    def test_fix_queries_site(self, monkeypatch: Any) -> None:
        self._check(_drive_fix_queries, monkeypatch)

    def test_query_budget_site(self, monkeypatch: Any) -> None:
        self._check(_drive_query_budget, monkeypatch)

    def test_project_diagnoser_site(self, monkeypatch: Any) -> None:
        self._check(_drive_project_diagnoser, monkeypatch)

    def test_celery_site(self, monkeypatch: Any) -> None:
        self._check(_drive_celery, monkeypatch)

    def test_pytest_plugin_site(self, monkeypatch: Any) -> None:
        self._check(_drive_pytest_plugin, monkeypatch)
