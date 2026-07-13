"""Tests for discover_analyzers() wiring across dispatch sites (3b).

Before this change, middleware.py, context_managers.py, check_queries.py,
celery_integration.py, and pytest_plugin.py each hardcoded their own narrow
subset of analyzer classes (3-5 out of 8). This replaced every site with
discover_analyzers(), relying on each analyzer's is_enabled() self-gate (3a)
to honor config toggles instead of bespoke per-site gating.

At this commit discover_analyzers() returns 8 analyzers (DRFSerializerAnalyzer
is deleted in 3c, dropping it to 7). Assertions here check presence/absence of
named analyzers, never a magic total count, so 3c's deletion doesn't require
touching these tests.

Book.objects.all() selects exactly 8 explicit columns (id, title, isbn,
author_id, publisher_id, price, description, published_date) -- at the
default fat_select threshold of 8 this reliably fires FAT_SELECT, an analyzer
none of the old hardcoded lists ever included. Its presence proves
discover_analyzers() wiring actually reached each site, not just that queries
were captured.
"""

from __future__ import annotations

import json
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory, override_settings

from query_doctor.celery_integration import diagnose_task
from query_doctor.conf import get_config
from query_doctor.context_managers import diagnose_queries
from query_doctor.middleware import QueryDoctorMiddleware
from query_doctor.plugin_api import discover_analyzers
from query_doctor.types import DiagnosisReport, IssueType
from tests.factories import BookFactory


class TestDiscoverAnalyzersMembership:
    """discover_analyzers() must include every built-in, by name."""

    def test_widened_set_present_by_name(self) -> None:
        names = {a.name for a in discover_analyzers()}
        for expected in (
            "nplusone",
            "duplicate",
            "missing_index",
            "fat_select",
            "queryset_eval",
            "drf_serializer",
            "complexity",
        ):
            assert expected in names


@pytest.mark.django_db
class TestContextManagerWiring:
    """context_managers.py must reach analyzers beyond the old narrow 3."""

    def test_fat_select_reachable(self) -> None:
        BookFactory()

        with diagnose_queries() as report:
            from tests.testapp.models import Book

            list(Book.objects.all())

        types = [p.issue_type for p in report.prescriptions]
        assert IssueType.FAT_SELECT in types


@pytest.mark.django_db
class TestCheckQueriesWiring:
    """check_queries.py must reach analyzers beyond the old narrow 3."""

    def test_fat_select_reachable(self) -> None:
        for _ in range(5):
            BookFactory()

        out = StringIO()
        call_command("check_queries", "--format", "json", "--url", "/books/nplusone/", stdout=out)
        data = json.loads(out.getvalue())
        types = [p["issue_type"] for p in data["prescriptions"]]
        assert IssueType.FAT_SELECT.value in types


@pytest.mark.django_db
class TestCeleryWiring:
    """celery_integration.py must reach analyzers beyond the old narrow 3."""

    def test_fat_select_reachable(self) -> None:
        reports: list[DiagnosisReport] = []

        @diagnose_task(on_report=reports.append)
        def db_task() -> str:
            from tests.testapp.models import Book

            BookFactory()
            list(Book.objects.all())
            return "done"

        db_task()

        assert len(reports) == 1
        types = [p.issue_type for p in reports[0].prescriptions]
        assert IssueType.FAT_SELECT in types


@pytest.mark.django_db
class TestPytestPluginWiring:
    """pytest_plugin.py must reach analyzers beyond the old narrow 5.

    fat_select is a poor witness here: pytest_plugin's old hardcoded list
    already included nplusone, duplicate, missing_index, fat_select, and
    queryset_eval -- only complexity/drf_serializer/serializer_method were
    missing, and the latter two are hardwired to always return [] regardless
    of wiring. complexity is the only analyzer whose presence actually proves
    this site's list was replaced with discover_analyzers().
    """

    def test_complexity_reachable(self) -> None:
        from query_doctor.pytest_plugin import _run_analyzers
        from query_doctor.types import CallSite, CapturedQuery

        callsite = CallSite(filepath="views.py", line_number=1, function_name="get_queryset")
        sql = (
            "SELECT b.id FROM books b "
            "JOIN a ON 1=1 JOIN b2 ON 1=1 JOIN c ON 1=1 "
            "JOIN d ON 1=1 JOIN e ON 1=1"
        )
        query = CapturedQuery(
            sql=sql,
            params=None,
            duration_ms=1.0,
            fingerprint="abc123",
            normalized_sql=sql.lower(),
            callsite=callsite,
            is_select=True,
            tables=["books"],
        )

        report = DiagnosisReport()
        _run_analyzers(report, [query])

        types = [p.issue_type for p in report.prescriptions]
        assert IssueType.QUERY_COMPLEXITY in types


def _fat_select_view(request: HttpRequest) -> HttpResponse:
    """View that selects every column on Book (8 cols, meets default threshold)."""
    from tests.testapp.models import Book

    list(Book.objects.all())
    return HttpResponse("OK")


def _run_middleware_capture(view: object) -> DiagnosisReport | None:
    """Run the middleware against a view, capturing the report via a mock reporter."""
    mock_reporter = MagicMock()
    with patch("query_doctor.middleware._get_reporters", return_value=[mock_reporter]):
        middleware = QueryDoctorMiddleware(view)  # type: ignore[arg-type]
        request = RequestFactory().get("/books/")
        middleware(request)

    if not mock_reporter.report.called:
        return None
    result: DiagnosisReport = mock_reporter.report.call_args[0][0]
    return result


@pytest.mark.django_db
class TestMiddlewareWiring:
    """middleware.py must reach analyzers beyond the old narrow 3, and its
    gating must flip from the deleted upstream _get_enabled_analyzers filter
    to each analyzer's own is_enabled() self-gate without losing coverage.
    """

    def test_fat_select_reachable(self) -> None:
        BookFactory()

        report = _run_middleware_capture(_fat_select_view)

        assert report is not None
        types = [p.issue_type for p in report.prescriptions]
        assert IssueType.FAT_SELECT in types

    def test_disabled_analyzer_absent_via_middleware(self) -> None:
        """nplusone.enabled=False must suppress N+1 findings via the real
        middleware dispatch path, now that middleware relies on the 3a
        self-gate instead of its own deleted upstream filter.
        """
        for _ in range(5):
            BookFactory()

        with override_settings(QUERY_DOCTOR={"ANALYZERS": {"nplusone": {"enabled": False}}}):
            get_config.cache_clear()
            report = _run_middleware_capture(_nplusone_view)
            get_config.cache_clear()

        types = [p.issue_type for p in report.prescriptions] if report else []
        assert IssueType.N_PLUS_ONE not in types

    def test_enabled_analyzer_positive_control_via_middleware(self) -> None:
        """Positive control paired with the disabled test above: same
        fixture, nplusone enabled -> N+1 must be present.
        """
        for _ in range(5):
            BookFactory()

        with override_settings(QUERY_DOCTOR={"ANALYZERS": {"nplusone": {"enabled": True}}}):
            get_config.cache_clear()
            report = _run_middleware_capture(_nplusone_view)
            get_config.cache_clear()

        assert report is not None
        types = [p.issue_type for p in report.prescriptions]
        assert IssueType.N_PLUS_ONE in types


def _nplusone_view(request: HttpRequest) -> HttpResponse:
    """View that triggers N+1 queries by accessing .author on each book."""
    from tests.testapp.models import Book

    for book in Book.objects.all():
        _ = book.author.name
    return HttpResponse("OK")
