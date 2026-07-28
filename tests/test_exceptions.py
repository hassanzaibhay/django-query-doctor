"""Tests for query_doctor.exceptions."""

from __future__ import annotations

from query_doctor.exceptions import (
    QueryBudgetError,
    QueryDoctorError,
)


class TestExceptions:
    """Tests for the exception hierarchy."""

    def test_base_exception_is_exception(self) -> None:
        assert issubclass(QueryDoctorError, Exception)

    def test_budget_error_inherits(self) -> None:
        assert issubclass(QueryBudgetError, QueryDoctorError)

    def test_budget_error_has_report(self) -> None:
        err = QueryBudgetError("over budget")
        assert err.report is None
        assert str(err) == "over budget"

    def test_can_raise_and_catch(self) -> None:
        """A subclass must be catchable via the base class, message intact.

        Uses QueryBudgetError because it is now the only QueryDoctorError
        subclass; the property under test is the single-except-clause contract
        the module docstring promises, not this particular exception.
        """
        try:
            raise QueryBudgetError("over budget")
        except QueryDoctorError as e:
            assert str(e) == "over budget"
