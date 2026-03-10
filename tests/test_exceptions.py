"""Tests for query_doctor.exceptions."""

from __future__ import annotations

from query_doctor.exceptions import (
    AnalyzerError,
    ConfigError,
    InterceptorError,
    QueryBudgetError,
    QueryDoctorError,
)


class TestExceptions:
    """Tests for the exception hierarchy."""

    def test_base_exception_is_exception(self) -> None:
        assert issubclass(QueryDoctorError, Exception)

    def test_config_error_inherits(self) -> None:
        assert issubclass(ConfigError, QueryDoctorError)

    def test_analyzer_error_inherits(self) -> None:
        assert issubclass(AnalyzerError, QueryDoctorError)

    def test_interceptor_error_inherits(self) -> None:
        assert issubclass(InterceptorError, QueryDoctorError)

    def test_budget_error_inherits(self) -> None:
        assert issubclass(QueryBudgetError, QueryDoctorError)

    def test_budget_error_has_report(self) -> None:
        err = QueryBudgetError("over budget")
        assert err.report is None
        assert str(err) == "over budget"

    def test_can_raise_and_catch(self) -> None:
        try:
            raise ConfigError("bad config")
        except QueryDoctorError as e:
            assert str(e) == "bad config"
