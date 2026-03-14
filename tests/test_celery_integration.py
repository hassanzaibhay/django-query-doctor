"""Tests for Celery task integration.

Verifies the @diagnose_task decorator works with and without Celery installed,
preserves return values, propagates exceptions, and captures queries.
"""

from __future__ import annotations

import pytest

from query_doctor.celery_integration import diagnose_task
from query_doctor.types import DiagnosisReport


class TestDiagnoseTaskWithoutCelery:
    """Tests for @diagnose_task when Celery is not installed."""

    def test_decorator_is_passthrough(self) -> None:
        """Without Celery, decorator should return the original function."""

        @diagnose_task
        def my_task() -> str:
            return "result"

        assert my_task() == "result"

    def test_preserves_function_name(self) -> None:
        """Decorated function should preserve its name."""

        @diagnose_task
        def my_task() -> str:
            return "ok"

        assert my_task.__wrapped__.__name__ == "my_task" or "my_task" in str(my_task)

    def test_no_crash_without_celery(self) -> None:
        """Should never crash if Celery is not installed."""

        @diagnose_task
        def task_func() -> int:
            return 42

        assert task_func() == 42


class TestDiagnoseTaskReturnValues:
    """Tests that return values are preserved."""

    def test_returns_none(self) -> None:
        """Task returning None should work."""

        @diagnose_task
        def void_task() -> None:
            pass

        assert void_task() is None

    def test_returns_complex_value(self) -> None:
        """Task returning complex values should work."""

        @diagnose_task
        def complex_task() -> dict[str, list[int]]:
            return {"numbers": [1, 2, 3]}

        result = complex_task()
        assert result == {"numbers": [1, 2, 3]}


class TestDiagnoseTaskExceptions:
    """Tests that exceptions propagate correctly."""

    def test_exception_propagates(self) -> None:
        """Task exceptions should not be swallowed by the decorator."""

        @diagnose_task
        def failing_task() -> None:
            raise ValueError("Task failed")

        with pytest.raises(ValueError, match="Task failed"):
            failing_task()

    def test_runtime_error_propagates(self) -> None:
        """RuntimeError should propagate through decorator."""

        @diagnose_task
        def bad_task() -> None:
            raise RuntimeError("Something went wrong")

        with pytest.raises(RuntimeError, match="Something went wrong"):
            bad_task()


class TestDiagnoseTaskQueryCapture:
    """Tests that queries are captured during task execution."""

    @pytest.mark.django_db
    def test_captures_queries(self) -> None:
        """Queries made during task should be captured and analyzed."""
        reports: list[DiagnosisReport] = []

        @diagnose_task(on_report=lambda r: reports.append(r))
        def db_task() -> str:
            from tests.testapp.models import Book

            list(Book.objects.all())
            return "done"

        result = db_task()

        assert result == "done"
        assert len(reports) == 1
        assert reports[0].total_queries >= 1

    @pytest.mark.django_db
    def test_no_issues_clean_task(self) -> None:
        """Clean task should report no issues."""
        reports: list[DiagnosisReport] = []

        @diagnose_task(on_report=lambda r: reports.append(r))
        def clean_task() -> str:
            return "clean"

        clean_task()

        assert len(reports) == 1
        assert reports[0].issues == 0


class TestDiagnoseTaskWithCallbackArgs:
    """Tests for decorator with arguments."""

    def test_decorator_with_parens(self) -> None:
        """@diagnose_task() with parens should work."""

        @diagnose_task()
        def my_task() -> str:
            return "ok"

        assert my_task() == "ok"

    def test_decorator_without_parens(self) -> None:
        """@diagnose_task without parens should work."""

        @diagnose_task
        def my_task() -> str:
            return "ok"

        assert my_task() == "ok"

    @pytest.mark.django_db
    def test_on_report_callback(self) -> None:
        """on_report callback should receive the diagnosis report."""
        captured: list[DiagnosisReport] = []

        @diagnose_task(on_report=captured.append)
        def task_with_callback() -> None:
            from tests.testapp.models import Publisher

            list(Publisher.objects.all())

        task_with_callback()

        assert len(captured) == 1
        assert isinstance(captured[0], DiagnosisReport)


class TestDiagnoseTaskEdgeCases:
    """Edge case tests."""

    def test_task_with_args(self) -> None:
        """Decorated task with positional args should work."""

        @diagnose_task
        def add(a: int, b: int) -> int:
            return a + b

        assert add(3, 4) == 7

    def test_task_with_kwargs(self) -> None:
        """Decorated task with keyword args should work."""

        @diagnose_task
        def greet(name: str = "world") -> str:
            return f"hello {name}"

        assert greet(name="django") == "hello django"

    def test_module_docstring(self) -> None:
        """Module should have a docstring."""
        import query_doctor.celery_integration

        assert query_doctor.celery_integration.__doc__
