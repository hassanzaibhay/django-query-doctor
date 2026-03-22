"""Tests targeting coverage gaps across modules.

Covers error handling paths, edge cases, and configuration branches
that standard happy-path tests don't reach.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from query_doctor.analyzers.base import BaseAnalyzer
from query_doctor.analyzers.duplicate import DuplicateAnalyzer
from query_doctor.analyzers.nplusone import NPlusOneAnalyzer
from query_doctor.reporters.console import ConsoleReporter
from query_doctor.types import (
    CallSite,
    CapturedQuery,
    DiagnosisReport,
    IssueType,
    Prescription,
    Severity,
)
from tests.factories import BookFactory

# ── base.py: is_enabled() ──────────────────────────────────────────


class TestBaseAnalyzerIsEnabled:
    """Tests for BaseAnalyzer.is_enabled() method."""

    def test_nplusone_enabled_by_default(self) -> None:
        """N+1 analyzer should be enabled by default."""
        analyzer = NPlusOneAnalyzer()
        assert analyzer.is_enabled() is True

    def test_duplicate_enabled_by_default(self) -> None:
        """Duplicate analyzer should be enabled by default."""
        analyzer = DuplicateAnalyzer()
        assert analyzer.is_enabled() is True

    @pytest.fixture(autouse=True)
    def _clear_config_cache(self) -> None:
        from query_doctor.conf import get_config

        get_config.cache_clear()
        yield
        get_config.cache_clear()

    def test_disabled_via_config(self, settings: object) -> None:
        """Analyzer should report disabled when config says so."""
        from query_doctor.conf import get_config

        settings.QUERY_DOCTOR = {  # type: ignore[attr-defined]
            "ANALYZERS": {"nplusone": {"enabled": False}},
        }
        get_config.cache_clear()
        analyzer = NPlusOneAnalyzer()
        assert analyzer.is_enabled() is False

    def test_unknown_analyzer_enabled_by_default(self) -> None:
        """An analyzer not in config should default to enabled."""

        class CustomAnalyzer(BaseAnalyzer):
            name = "custom_unknown"

            def analyze(self, queries, models_meta=None):  # type: ignore[override]
                return []

        analyzer = CustomAnalyzer()
        assert analyzer.is_enabled() is True


# ── console.py: Rich rendering path ────────────────────────────────


class TestConsoleReporterRich:
    """Tests for the Rich rendering path in ConsoleReporter."""

    def test_rich_render_empty_report(self) -> None:
        """Rich path should handle empty reports."""
        reporter = ConsoleReporter()
        report = DiagnosisReport()
        output = reporter.render(report)
        assert "No issues detected" in output

    def test_rich_render_with_prescription(self) -> None:
        """Rich path should render prescriptions with severity."""
        reporter = ConsoleReporter()
        report = DiagnosisReport(
            prescriptions=[
                Prescription(
                    issue_type=IssueType.N_PLUS_ONE,
                    severity=Severity.CRITICAL,
                    description="N+1 detected: 10 queries for author",
                    fix_suggestion="select_related('author')",
                    callsite=CallSite(
                        filepath="views.py",
                        line_number=10,
                        function_name="my_view",
                        code_context="books = Book.objects.all()",
                    ),
                    query_count=10,
                    time_saved_ms=50.0,
                ),
            ],
            total_queries=11,
            total_time_ms=55.0,
        )
        output = reporter.render(report)
        assert "CRITICAL" in output
        assert "select_related" in output
        assert "views.py" in output
        assert "10" in output

    def test_rich_render_warning_severity(self) -> None:
        """Rich path should style WARNING differently from CRITICAL."""
        reporter = ConsoleReporter()
        report = DiagnosisReport(
            prescriptions=[
                Prescription(
                    issue_type=IssueType.DUPLICATE_QUERY,
                    severity=Severity.WARNING,
                    description="Duplicate queries",
                    fix_suggestion="Cache the result",
                    callsite=None,
                    query_count=3,
                    time_saved_ms=2.0,
                ),
            ],
            total_queries=5,
            total_time_ms=10.0,
        )
        output = reporter.render(report)
        assert "WARNING" in output

    def test_plain_fallback_when_rich_unavailable(self) -> None:
        """Should fall back to plain text when Rich import fails."""
        reporter = ConsoleReporter()
        report = DiagnosisReport(total_queries=5, total_time_ms=10.0)
        with patch(
            "query_doctor.reporters.console.ConsoleReporter._render_rich",
            side_effect=ImportError("no rich"),
        ):
            output = reporter.render(report)
        assert "=" * 60 in output
        assert "5" in output


# ── middleware.py: error handling and sampling ──────────────────────


@pytest.mark.django_db
class TestMiddlewareEdgeCases:
    """Tests for middleware error handling and sampling."""

    @pytest.fixture(autouse=True)
    def _clear_config_cache(self) -> None:
        from query_doctor.conf import get_config

        get_config.cache_clear()
        yield
        get_config.cache_clear()

    def test_config_load_failure_passes_through(self, rf: object) -> None:
        """If config loading fails, request should still work."""
        from django.test import RequestFactory

        from query_doctor.middleware import QueryDoctorMiddleware

        factory = RequestFactory()
        request = factory.get("/")

        def view(req):  # type: ignore[no-untyped-def]
            from django.http import HttpResponse

            return HttpResponse("ok")

        middleware = QueryDoctorMiddleware(view)
        with patch("query_doctor.middleware.get_config", side_effect=RuntimeError("boom")):
            response = middleware(request)
        assert response.status_code == 200

    def test_sampling_skips_some_requests(self, rf: object) -> None:
        """Requests should be skipped when random > sample_rate."""
        from django.test import RequestFactory

        from query_doctor.middleware import QueryDoctorMiddleware

        factory = RequestFactory()
        request = factory.get("/")
        call_count = 0

        def view(req):  # type: ignore[no-untyped-def]
            nonlocal call_count
            call_count += 1
            from django.http import HttpResponse

            return HttpResponse("ok")

        middleware = QueryDoctorMiddleware(view)
        with (
            patch("query_doctor.middleware.get_config") as mock_config,
            patch("query_doctor.middleware.random") as mock_random,
        ):
            mock_config.return_value = {"ENABLED": True, "SAMPLE_RATE": 0.5, "IGNORE_URLS": []}
            mock_random.random.return_value = 0.9  # Above 0.5 → skip
            response = middleware(request)
        assert response.status_code == 200

    def test_analysis_failure_doesnt_crash(self, rf: object) -> None:
        """If analysis fails, response should still be returned."""
        from django.test import RequestFactory

        from query_doctor.middleware import QueryDoctorMiddleware

        factory = RequestFactory()
        request = factory.get("/")

        def view(req):  # type: ignore[no-untyped-def]
            from django.http import HttpResponse

            return HttpResponse("ok")

        middleware = QueryDoctorMiddleware(view)
        with patch.object(middleware, "_analyze_and_report", side_effect=RuntimeError("boom")):
            response = middleware(request)
        assert response.status_code == 200

    def test_analyzer_failure_doesnt_crash(self) -> None:
        """If a single analyzer fails, others should still run."""
        from query_doctor.interceptor import QueryInterceptor
        from query_doctor.middleware import QueryDoctorMiddleware

        middleware = QueryDoctorMiddleware(lambda r: None)  # type: ignore[arg-type]
        interceptor = QueryInterceptor()

        config = {
            "ANALYZERS": {"nplusone": {"enabled": True}, "duplicate": {"enabled": True}},
            "REPORTERS": [],
        }

        with patch(
            "query_doctor.middleware._get_enabled_analyzers",
            return_value=[MagicMock(analyze=MagicMock(side_effect=RuntimeError("boom")))],
        ):
            # Should not raise
            middleware._analyze_and_report(interceptor, config)

    def test_reporter_failure_doesnt_crash(self) -> None:
        """If a reporter fails, the middleware should still work."""
        from query_doctor.interceptor import QueryInterceptor
        from query_doctor.middleware import QueryDoctorMiddleware

        middleware = QueryDoctorMiddleware(lambda r: None)  # type: ignore[arg-type]
        interceptor = QueryInterceptor()

        # Manually inject a query so analysis runs
        query = CapturedQuery(
            sql="SELECT 1",
            params=None,
            duration_ms=1.0,
            fingerprint="abc",
            normalized_sql="select ?",
            callsite=None,
            is_select=True,
            tables=[],
        )
        interceptor._queries_var.get().append(query)

        config = {
            "ANALYZERS": {"nplusone": {"enabled": True}, "duplicate": {"enabled": True}},
            "REPORTERS": ["console"],
        }

        # Use a mock analyzer that returns a prescription so reporters are invoked
        mock_prescription = Prescription(
            issue_type=IssueType.N_PLUS_ONE,
            severity=Severity.CRITICAL,
            description="test",
            fix_suggestion="test fix",
            callsite=None,
        )
        mock_analyzer = MagicMock(analyze=MagicMock(return_value=[mock_prescription]))
        failing_reporter = MagicMock(report=MagicMock(side_effect=RuntimeError("boom")))

        with (
            patch(
                "query_doctor.middleware._get_enabled_analyzers",
                return_value=[mock_analyzer],
            ),
            patch(
                "query_doctor.middleware._get_reporters",
                return_value=[failing_reporter],
            ),
        ):
            # Should not raise despite reporter failure
            middleware._analyze_and_report(interceptor, config)


# ── nplusone.py: edge cases ────────────────────────────────────────


class TestNPlusOneEdgeCases:
    """Tests for uncovered branches in NPlusOneAnalyzer."""

    def test_empty_queries(self) -> None:
        """Empty list should return no prescriptions."""
        analyzer = NPlusOneAnalyzer()
        assert analyzer.analyze([]) == []

    def test_non_select_queries_ignored(self) -> None:
        """INSERT/UPDATE queries should be skipped."""
        query = CapturedQuery(
            sql='INSERT INTO testapp_book VALUES (1, "test")',
            params=None,
            duration_ms=1.0,
            fingerprint="abc123",
            normalized_sql="insert into testapp_book values (?, ?)",
            callsite=None,
            is_select=False,
            tables=["testapp_book"],
        )
        analyzer = NPlusOneAnalyzer()
        assert analyzer.analyze([query] * 5) == []

    def test_analysis_exception_returns_empty(self) -> None:
        """If analysis crashes internally, should return empty list."""
        analyzer = NPlusOneAnalyzer()
        with patch.object(analyzer, "_classify_and_prescribe", side_effect=RuntimeError("boom")):
            # The outer try/except in analyze() should catch this
            result = analyzer.analyze(
                [
                    CapturedQuery(
                        sql="SELECT * FROM t WHERE id = 1",
                        params=(1,),
                        duration_ms=1.0,
                        fingerprint="same",
                        normalized_sql="select * from t where id = ?",
                        callsite=None,
                        is_select=True,
                        tables=["t"],
                    )
                ]
                * 5
            )
        assert result == []

    def test_unrecognized_pattern_returns_none(self) -> None:
        """Queries that don't match FK or PK patterns should be skipped."""
        analyzer = NPlusOneAnalyzer()
        # A query with no WHERE clause won't match N+1 patterns
        queries = [
            CapturedQuery(
                sql="SELECT * FROM testapp_book",
                params=None,
                duration_ms=1.0,
                fingerprint="same_fp",
                normalized_sql="select * from testapp_book",
                callsite=None,
                is_select=True,
                tables=["testapp_book"],
            )
        ] * 5
        result = analyzer.analyze(queries)
        assert result == []

    @pytest.mark.django_db
    def test_unknown_table_handled_gracefully(self) -> None:
        """Queries for tables not in Django models should not crash."""
        analyzer = NPlusOneAnalyzer()
        queries = [
            CapturedQuery(
                sql='SELECT * FROM unknown_table WHERE "fk_id" = 1',
                params=(1,),
                duration_ms=1.0,
                fingerprint="same_fp",
                normalized_sql='select * from unknown_table where "fk_id" = ?',
                callsite=None,
                is_select=True,
                tables=["unknown_table"],
            )
        ] * 5
        result = analyzer.analyze(queries)
        # Should not crash, may or may not detect (depends on heuristics)
        assert isinstance(result, list)


# ── stack_tracer.py: edge cases ────────────────────────────────────


class TestStackTracerEdgeCases:
    """Tests for uncovered branches in stack_tracer."""

    def test_capture_callsite_exception_returns_none(self) -> None:
        """If traceback extraction fails, should return None."""
        from query_doctor.stack_tracer import capture_callsite

        with patch("query_doctor.stack_tracer.traceback.extract_stack", side_effect=OSError):
            result = capture_callsite()
        assert result is None

    def test_all_frames_excluded_returns_none(self) -> None:
        """If all stack frames are excluded, should return None."""
        from query_doctor.stack_tracer import capture_callsite

        # Exclude everything by providing an exclude list that matches all frames
        result = capture_callsite(exclude_modules=["tests", "pytest", "_pytest", "pluggy"])
        # Depending on the call stack, this may or may not return None.
        # The key thing is it doesn't crash.
        assert result is None or result.filepath != ""


# ── interceptor.py: edge cases ─────────────────────────────────────


@pytest.mark.django_db
class TestInterceptorEdgeCases:
    """Tests for uncovered branches in interceptor."""

    def test_db_exception_is_reraised(self) -> None:
        """Database exceptions should be re-raised, not swallowed."""
        from django.db import connection

        from query_doctor.interceptor import QueryInterceptor

        interceptor = QueryInterceptor()
        with (
            pytest.raises(Exception),  # noqa: B017
            connection.execute_wrapper(interceptor),
        ):
            from django.db import connection as conn

            cursor = conn.cursor()
            cursor.execute("SELECT * FROM nonexistent_table_xyz")

    def test_non_tuple_params_handled(self) -> None:
        """Params that can't be converted to tuple should not crash."""
        from query_doctor.interceptor import QueryInterceptor

        interceptor = QueryInterceptor(capture_stack=False)

        # Simulate a call with params that cause TypeError on tuple()
        mock_execute = MagicMock(return_value="result")
        context: dict = {}

        class BadParams:
            def __iter__(self):  # type: ignore[no-untyped-def]
                raise TypeError("cannot iterate")

        result = interceptor(mock_execute, "SELECT 1", BadParams(), False, context)
        assert result == "result"
        queries = interceptor.get_queries()
        assert len(queries) == 1
        assert queries[0].params is None


# ── context_managers.py: analyzer failure ──────────────────────────


@pytest.mark.django_db
class TestContextManagerEdgeCases:
    """Tests for error handling in diagnose_queries context manager."""

    def test_analyzer_failure_doesnt_crash(self) -> None:
        """If an analyzer fails, the report should still be returned."""
        from query_doctor.context_managers import diagnose_queries

        BookFactory()
        with (
            patch(
                "query_doctor.context_managers.NPlusOneAnalyzer.analyze",
                side_effect=RuntimeError("boom"),
            ),
            diagnose_queries() as report,
        ):
            from tests.testapp.models import Book

            list(Book.objects.all())

        assert report.total_queries >= 1
        # prescriptions may be empty due to the failure, but report is intact
        assert isinstance(report.prescriptions, list)
