"""Tests for decorators in query_doctor.decorators."""

from __future__ import annotations

import pytest

from query_doctor.types import IssueType
from tests.factories import BookFactory


class TestDiagnoseDecorator:
    """Tests for the @diagnose decorator."""

    def test_returns_function_result(self) -> None:
        """Decorated function should return its normal result."""
        from query_doctor.decorators import diagnose

        @diagnose
        def my_func() -> str:
            return "hello"

        assert my_func() == "hello"

    @pytest.mark.django_db
    def test_attaches_report_to_function(self) -> None:
        """After execution, the function should have a _query_doctor_report attribute."""
        from query_doctor.decorators import diagnose

        @diagnose
        def my_func() -> str:
            from tests.testapp.models import Book

            list(Book.objects.all())
            return "done"

        BookFactory()
        my_func()
        assert hasattr(my_func, "_query_doctor_report")
        assert my_func._query_doctor_report.total_queries >= 1

    @pytest.mark.django_db
    def test_detects_nplusone(self) -> None:
        """Should detect N+1 queries in the decorated function."""
        from query_doctor.decorators import diagnose

        for _ in range(5):
            BookFactory()

        @diagnose
        def bad_func() -> list[str]:
            from tests.testapp.models import Book

            return [book.author.name for book in Book.objects.all()]

        bad_func()
        report = bad_func._query_doctor_report
        assert any(p.issue_type == IssueType.N_PLUS_ONE for p in report.prescriptions)

    def test_preserves_function_metadata(self) -> None:
        """Decorator should preserve __name__ and __doc__."""
        from query_doctor.decorators import diagnose

        @diagnose
        def my_view() -> None:
            """My docstring."""

        assert my_view.__name__ == "my_view"
        assert my_view.__doc__ == "My docstring."

    def test_handles_function_args(self) -> None:
        """Decorated function should pass through args and kwargs."""
        from query_doctor.decorators import diagnose

        @diagnose
        def add(a: int, b: int, *, extra: int = 0) -> int:
            return a + b + extra

        assert add(1, 2, extra=3) == 6

    @pytest.mark.django_db
    def test_never_crashes_on_analysis_error(self) -> None:
        """If analysis fails, the function should still return normally."""
        from unittest.mock import patch

        from query_doctor.decorators import diagnose

        @diagnose
        def my_func() -> str:
            from tests.testapp.models import Book

            list(Book.objects.all())
            return "ok"

        with patch(
            "query_doctor.decorators.diagnose_queries",
            side_effect=RuntimeError("boom"),
        ):
            result = my_func()
            assert result == "ok"


class TestQueryBudgetDecorator:
    """Tests for the @query_budget decorator."""

    @pytest.mark.django_db
    def test_under_budget_no_error(self) -> None:
        """Function under budget should execute normally."""
        from query_doctor.decorators import query_budget

        @query_budget(max_queries=50)
        def my_func() -> str:
            from tests.testapp.models import Book

            list(Book.objects.all())
            return "ok"

        assert my_func() == "ok"

    @pytest.mark.django_db
    def test_over_query_budget_raises(self) -> None:
        """Exceeding max_queries should raise QueryBudgetError."""
        from query_doctor.decorators import query_budget
        from query_doctor.exceptions import QueryBudgetError

        for _ in range(5):
            BookFactory()

        @query_budget(max_queries=1)
        def bad_func() -> None:
            from tests.testapp.models import Book

            for book in Book.objects.all():
                _ = book.author.name

        with pytest.raises(QueryBudgetError, match="max_queries"):
            bad_func()

    @pytest.mark.django_db
    def test_over_time_budget_raises(self) -> None:
        """Exceeding max_time_ms should raise QueryBudgetError."""
        from unittest.mock import patch

        from query_doctor.decorators import query_budget
        from query_doctor.exceptions import QueryBudgetError

        @query_budget(max_time_ms=0.0001)
        def slow_func() -> None:
            from tests.testapp.models import Book

            list(Book.objects.all())

        BookFactory()
        # Patch to simulate high time
        with (
            patch(
                "query_doctor.decorators._get_report_time_ms",
                return_value=100.0,
            ),
            pytest.raises(QueryBudgetError, match="max_time_ms"),
        ):
            slow_func()

    def test_preserves_function_metadata(self) -> None:
        """Decorator should preserve __name__ and __doc__."""
        from query_doctor.decorators import query_budget

        @query_budget(max_queries=10)
        def my_view() -> None:
            """My docstring."""

        assert my_view.__name__ == "my_view"
        assert my_view.__doc__ == "My docstring."

    def test_handles_function_args(self) -> None:
        """Decorated function should pass through args and kwargs."""
        from query_doctor.decorators import query_budget

        @query_budget(max_queries=100)
        def add(a: int, b: int) -> int:
            return a + b

        assert add(3, 4) == 7

    @pytest.mark.django_db
    def test_budget_uses_config_defaults(self) -> None:
        """Should fall back to config defaults when no explicit budget given."""
        from query_doctor.decorators import query_budget

        @query_budget()
        def my_func() -> str:
            return "ok"

        # No budget set (defaults are None) → should not raise
        assert my_func() == "ok"

    @pytest.mark.django_db
    def test_budget_report_attached(self) -> None:
        """The DiagnosisReport should be attached to the function after execution."""
        from query_doctor.decorators import query_budget

        @query_budget(max_queries=100)
        def my_func() -> str:
            from tests.testapp.models import Book

            list(Book.objects.all())
            return "done"

        BookFactory()
        my_func()
        assert hasattr(my_func, "_query_doctor_report")

    @pytest.mark.django_db
    def test_exception_includes_report(self) -> None:
        """QueryBudgetError should include the report."""
        from query_doctor.decorators import query_budget
        from query_doctor.exceptions import QueryBudgetError

        for _ in range(5):
            BookFactory()

        @query_budget(max_queries=1)
        def bad_func() -> None:
            from tests.testapp.models import Book

            for book in Book.objects.all():
                _ = book.author.name

        with pytest.raises(QueryBudgetError) as exc_info:
            bad_func()

        assert exc_info.value.report is not None
        assert exc_info.value.report.total_queries > 1
