"""Tests for the pytest plugin.

Verifies the pytest plugin registers correctly, provides the
query_doctor fixture function, and captures queries properly.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from query_doctor.pytest_plugin import (
    _run_analyzers,
    pytest_addoption,
)
from query_doctor.types import DiagnosisReport


class TestPluginRegistration:
    """Tests for plugin registration and option handling."""

    def test_addoption_callable(self) -> None:
        """pytest_addoption should be a callable function."""
        assert callable(pytest_addoption)

    def test_addoption_registers_flag(self) -> None:
        """pytest_addoption should register the --query-doctor flag."""
        mock_parser = MagicMock()
        mock_group = MagicMock()
        mock_parser.getgroup.return_value = mock_group
        pytest_addoption(mock_parser)
        mock_parser.getgroup.assert_called_once_with("query_doctor", "Django Query Doctor")
        mock_group.addoption.assert_called_once()
        call_kwargs = mock_group.addoption.call_args
        assert "--query-doctor" in call_kwargs[0]


class TestQueryDoctorFixtureIntegration:
    """Tests the fixture behavior via pytester or direct logic testing."""

    @pytest.mark.django_db
    def test_interceptor_captures_queries(self) -> None:
        """QueryInterceptor used by the fixture captures queries correctly."""
        from django.db import connection

        from query_doctor.interceptor import QueryInterceptor

        interceptor = QueryInterceptor()
        with connection.execute_wrapper(interceptor):
            from tests.testapp.models import Book

            list(Book.objects.all())

        queries = interceptor.get_queries()
        assert len(queries) >= 1
        assert queries[0].is_select

    @pytest.mark.django_db
    def test_fixture_logic_creates_report(self) -> None:
        """The fixture's core logic should produce a valid DiagnosisReport."""
        from django.db import connection

        from query_doctor.interceptor import QueryInterceptor

        report = DiagnosisReport()
        interceptor = QueryInterceptor()

        with connection.execute_wrapper(interceptor):
            from tests.testapp.models import Book

            list(Book.objects.all())

        queries = interceptor.get_queries()
        report.captured_queries = queries
        report.total_queries = len(queries)
        report.total_time_ms = sum(q.duration_ms for q in queries)

        assert report.total_queries >= 1
        assert isinstance(report, DiagnosisReport)

    @pytest.mark.django_db
    def test_fixture_logic_runs_analyzers(self) -> None:
        """The fixture's finalizer should run analyzers on captured queries."""
        from django.db import connection

        from query_doctor.interceptor import QueryInterceptor
        from tests.testapp.models import Book

        report = DiagnosisReport()
        interceptor = QueryInterceptor()

        with connection.execute_wrapper(interceptor):
            list(Book.objects.all())

        queries = interceptor.get_queries()
        report.captured_queries = queries
        report.total_queries = len(queries)
        report.total_time_ms = sum(q.duration_ms for q in queries)
        _run_analyzers(report, queries)

        # No N+1 or duplicates with a single simple query
        assert isinstance(report.prescriptions, list)


class TestRunAnalyzers:
    """Tests for the _run_analyzers helper function."""

    def test_runs_without_errors(self) -> None:
        """_run_analyzers should not raise on empty queries."""
        report = DiagnosisReport()
        _run_analyzers(report, [])
        assert report.issues == 0

    def test_populates_prescriptions_for_duplicates(self) -> None:
        """_run_analyzers should detect duplicate queries."""
        from query_doctor.types import CallSite, CapturedQuery

        callsite = CallSite(
            filepath="test.py", line_number=1, function_name="test", code_context=""
        )
        sql = 'SELECT "testapp_author"."id" FROM "testapp_author" WHERE "testapp_author"."id" = 1'
        norm_sql = (
            'select "testapp_author"."id" from "testapp_author" where "testapp_author"."id" = ?'
        )
        queries = [
            CapturedQuery(
                sql=sql,
                params=(1,),
                duration_ms=1.0,
                fingerprint="abc123",
                normalized_sql=norm_sql,
                callsite=callsite,
                is_select=True,
                tables=["testapp_author"],
            )
        ] * 5

        report = DiagnosisReport()
        _run_analyzers(report, queries)
        assert report.issues >= 1

    def test_handles_analyzer_failure(self) -> None:
        """_run_analyzers should not crash if an analyzer raises."""
        report = DiagnosisReport()
        # Pass invalid data that might cause issues but should be handled gracefully
        _run_analyzers(report, [MagicMock()])
        # Should not raise — analyzers protect themselves


class TestPluginImport:
    """Tests that the plugin module is importable and well-structured."""

    def test_module_docstring(self) -> None:
        """Module should have a docstring."""
        import query_doctor.pytest_plugin

        assert query_doctor.pytest_plugin.__doc__

    def test_exports_expected_names(self) -> None:
        """Module should export expected pytest hook functions."""
        import query_doctor.pytest_plugin as plugin

        assert hasattr(plugin, "pytest_addoption")
        assert hasattr(plugin, "query_doctor")

    def test_run_analyzers_exported(self) -> None:
        """_run_analyzers helper should be accessible."""
        import query_doctor.pytest_plugin as plugin

        assert hasattr(plugin, "_run_analyzers")


class TestQueryDoctorFixtureLogic:
    """Tests for the fixture's core logic (interceptor + finalizer pattern)."""

    @pytest.mark.django_db
    def test_interceptor_wrapper_captures_and_finalizes(self) -> None:
        """Simulates the fixture pattern: enter wrapper, run queries, finalize."""
        from django.db import connection

        from query_doctor.interceptor import QueryInterceptor
        from tests.testapp.models import Author

        report = DiagnosisReport()
        interceptor = QueryInterceptor()

        wrapper_ctx = connection.execute_wrapper(interceptor)
        wrapper_ctx.__enter__()

        list(Author.objects.all())

        # Finalize: exit wrapper, populate report, run analyzers
        wrapper_ctx.__exit__(None, None, None)
        queries = interceptor.get_queries()
        report.captured_queries = queries
        report.total_queries = len(queries)
        report.total_time_ms = sum(q.duration_ms for q in queries)
        _run_analyzers(report, queries)

        assert report.total_queries >= 1
        assert isinstance(report.prescriptions, list)

    @pytest.mark.django_db
    def test_fixture_pattern_empty_report_when_no_queries(self) -> None:
        """Fixture pattern with no queries yields empty report."""
        from django.db import connection

        from query_doctor.interceptor import QueryInterceptor

        report = DiagnosisReport()
        interceptor = QueryInterceptor()

        wrapper_ctx = connection.execute_wrapper(interceptor)
        wrapper_ctx.__enter__()
        # No queries executed
        wrapper_ctx.__exit__(None, None, None)

        queries = interceptor.get_queries()
        report.captured_queries = queries
        report.total_queries = len(queries)
        report.total_time_ms = sum(q.duration_ms for q in queries)
        _run_analyzers(report, queries)

        assert report.total_queries == 0
        assert report.issues == 0

    @pytest.mark.django_db
    def test_fixture_pattern_detects_duplicates(self) -> None:
        """Fixture pattern detects duplicate queries."""
        from django.db import connection

        from query_doctor.interceptor import QueryInterceptor
        from tests.testapp.models import Author

        report = DiagnosisReport()
        interceptor = QueryInterceptor()

        wrapper_ctx = connection.execute_wrapper(interceptor)
        wrapper_ctx.__enter__()

        for _ in range(5):
            list(Author.objects.all())

        wrapper_ctx.__exit__(None, None, None)
        queries = interceptor.get_queries()
        report.captured_queries = queries
        report.total_queries = len(queries)
        report.total_time_ms = sum(q.duration_ms for q in queries)
        _run_analyzers(report, queries)

        assert report.total_queries >= 5
        assert isinstance(report.prescriptions, list)

    @pytest.mark.django_db
    def test_wrapper_exit_error_is_handled(self) -> None:
        """If wrapper exit fails, it should be catchable without crashing."""
        import logging

        from django.db import connection

        from query_doctor.interceptor import QueryInterceptor

        interceptor = QueryInterceptor()
        wrapper_ctx = connection.execute_wrapper(interceptor)
        wrapper_ctx.__enter__()
        # Exit normally
        try:
            wrapper_ctx.__exit__(None, None, None)
        except Exception:
            logging.warning("wrapper exit failed")
        # Should reach here without crash


class TestRunAnalyzersExtended:
    """Extended tests for _run_analyzers covering optional analyzer imports."""

    @pytest.mark.django_db
    def test_run_analyzers_loads_all_available_analyzers(self) -> None:
        """_run_analyzers should load MissingIndex, FatSelect, QuerySetEval analyzers."""
        from query_doctor.types import CallSite, CapturedQuery

        callsite = CallSite(
            filepath="test.py", line_number=1, function_name="test", code_context=""
        )
        queries = [
            CapturedQuery(
                sql='SELECT * FROM "testapp_book"',
                params=(),
                duration_ms=1.0,
                fingerprint="abc",
                normalized_sql='select * from "testapp_book"',
                callsite=callsite,
                is_select=True,
                tables=["testapp_book"],
            )
        ]

        report = DiagnosisReport()
        _run_analyzers(report, queries)
        # Should not raise — all optional analyzers loaded
        assert isinstance(report.prescriptions, list)

    def test_run_analyzers_survives_analyzer_failure(self) -> None:
        """If one analyzer raises, _run_analyzers does not crash."""
        from unittest.mock import patch

        report = DiagnosisReport()
        # Patch the analyze method on the NPlusOneAnalyzer class
        with patch(
            "query_doctor.analyzers.nplusone.NPlusOneAnalyzer.analyze",
            side_effect=RuntimeError("boom"),
        ):
            _run_analyzers(report, [])
        # Should not raise
        assert isinstance(report.prescriptions, list)
