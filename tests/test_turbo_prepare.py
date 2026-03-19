"""Tests for QueryTurbo prepared statement strategies and backend detection."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from query_doctor.turbo.prepare import (
    NoPrepareStrategy,
    OracleImplicitCacheStrategy,
    PsycopgPrepareStrategy,
    clear_strategy_cache,
    get_prepare_strategy,
)


class TestNoPrepareStrategy:
    """NoPrepareStrategy is the fallback for unsupported backends."""

    def test_should_prepare_always_false(self):
        """NoPrepareStrategy never recommends preparation."""
        strategy = NoPrepareStrategy()
        assert strategy.should_prepare(0) is False
        assert strategy.should_prepare(5) is False
        assert strategy.should_prepare(100) is False

    def test_execute_delegates_to_cursor(self):
        """NoPrepareStrategy.execute() just calls cursor.execute()."""
        strategy = NoPrepareStrategy()
        cursor = MagicMock()
        sql = "SELECT * FROM books WHERE id = %s"
        params = (1,)

        strategy.execute(cursor, sql, params)

        cursor.execute.assert_called_once_with(sql, params)

    def test_execute_ignores_prepare_flag(self):
        """Even with prepare=True, NoPrepareStrategy calls normal execute."""
        strategy = NoPrepareStrategy()
        cursor = MagicMock()

        strategy.execute(cursor, "SELECT 1", (), prepare=True)

        cursor.execute.assert_called_once_with("SELECT 1", ())


class TestPsycopgPrepareStrategy:
    """PsycopgPrepareStrategy for PostgreSQL with psycopg3."""

    def test_should_prepare_below_threshold(self):
        """Below threshold, should_prepare returns False."""
        strategy = PsycopgPrepareStrategy(threshold=5)
        assert strategy.should_prepare(0) is False
        assert strategy.should_prepare(4) is False

    def test_should_prepare_at_threshold(self):
        """At threshold, should_prepare returns True."""
        strategy = PsycopgPrepareStrategy(threshold=5)
        assert strategy.should_prepare(5) is True

    def test_should_prepare_above_threshold(self):
        """Above threshold, should_prepare returns True."""
        strategy = PsycopgPrepareStrategy(threshold=5)
        assert strategy.should_prepare(10) is True
        assert strategy.should_prepare(100) is True

    def test_execute_with_prepare_true(self):
        """With prepare=True, passes it to cursor.execute()."""
        strategy = PsycopgPrepareStrategy(threshold=5)
        cursor = MagicMock()
        sql = "SELECT * FROM books WHERE id = %s"
        params = (1,)

        strategy.execute(cursor, sql, params, prepare=True)

        cursor.execute.assert_called_once_with(sql, params, prepare=True)

    def test_execute_without_prepare(self):
        """Without prepare, calls normal cursor.execute()."""
        strategy = PsycopgPrepareStrategy(threshold=5)
        cursor = MagicMock()

        strategy.execute(cursor, "SELECT 1", (), prepare=False)

        cursor.execute.assert_called_once_with("SELECT 1", ())

    def test_fallback_on_type_error(self):
        """If prepare=True raises TypeError, falls back and disables prepare."""
        strategy = PsycopgPrepareStrategy(threshold=5)
        cursor = MagicMock()
        cursor.execute.side_effect = [TypeError("unexpected keyword"), None]

        strategy.execute(cursor, "SELECT 1", (), prepare=True)

        # Should have been called twice: first with prepare=True (raises),
        # then without (fallback)
        assert cursor.execute.call_count == 2
        cursor.execute.assert_any_call("SELECT 1", (), prepare=True)
        cursor.execute.assert_any_call("SELECT 1", ())

    def test_prepare_disabled_after_type_error(self):
        """After TypeError, should_prepare returns False permanently."""
        strategy = PsycopgPrepareStrategy(threshold=5)
        cursor = MagicMock()
        cursor.execute.side_effect = [TypeError("unexpected keyword"), None]

        strategy.execute(cursor, "SELECT 1", (), prepare=True)

        # Now should_prepare should be disabled
        assert strategy.should_prepare(100) is False

    def test_fallback_on_other_exception(self):
        """On non-TypeError exceptions, falls back but doesn't disable."""
        strategy = PsycopgPrepareStrategy(threshold=5)
        cursor = MagicMock()
        cursor.execute.side_effect = [RuntimeError("something else"), None]

        strategy.execute(cursor, "SELECT 1", (), prepare=True)

        # Should fall back
        assert cursor.execute.call_count == 2
        # But should_prepare should NOT be disabled
        assert strategy.should_prepare(100) is True

    def test_custom_threshold(self):
        """Custom threshold is respected."""
        strategy = PsycopgPrepareStrategy(threshold=10)
        assert strategy.should_prepare(9) is False
        assert strategy.should_prepare(10) is True


class TestOracleImplicitCacheStrategy:
    """OracleImplicitCacheStrategy for Oracle databases."""

    def setup_method(self):
        """Reset the logged_once flag before each test."""
        OracleImplicitCacheStrategy._logged_once = False

    def test_should_prepare_always_false(self):
        """Oracle strategy never recommends explicit preparation."""
        strategy = OracleImplicitCacheStrategy()
        assert strategy.should_prepare(0) is False
        assert strategy.should_prepare(100) is False

    def test_execute_delegates_to_cursor(self):
        """Oracle strategy just calls cursor.execute() normally."""
        strategy = OracleImplicitCacheStrategy()
        cursor = MagicMock()

        strategy.execute(cursor, "SELECT 1", ())

        cursor.execute.assert_called_once_with("SELECT 1", ())


class TestBackendDetection:
    """Backend detection returns the correct strategy for each vendor."""

    def setup_method(self):
        """Clear strategy cache before each test."""
        clear_strategy_cache()

    def teardown_method(self):
        """Clear strategy cache after each test."""
        clear_strategy_cache()

    def test_sqlite_returns_no_prepare(self, settings):
        """SQLite backend returns NoPrepareStrategy."""
        settings.QUERY_DOCTOR = {"TURBO": {"ENABLED": True}}
        from query_doctor.conf import get_config

        get_config.cache_clear()

        conn = MagicMock()
        conn.vendor = "sqlite"

        strategy = get_prepare_strategy(conn)
        assert isinstance(strategy, NoPrepareStrategy)
        get_config.cache_clear()

    def test_mysql_returns_no_prepare(self, settings):
        """MySQL backend returns NoPrepareStrategy."""
        settings.QUERY_DOCTOR = {"TURBO": {"ENABLED": True}}
        from query_doctor.conf import get_config

        get_config.cache_clear()

        conn = MagicMock()
        conn.vendor = "mysql"

        strategy = get_prepare_strategy(conn)
        assert isinstance(strategy, NoPrepareStrategy)
        get_config.cache_clear()

    def test_postgresql_without_psycopg3_returns_no_prepare(self, settings):
        """PostgreSQL without psycopg3 returns NoPrepareStrategy."""
        settings.QUERY_DOCTOR = {"TURBO": {"ENABLED": True}}
        from query_doctor.conf import get_config

        get_config.cache_clear()

        conn = MagicMock()
        conn.vendor = "postgresql"

        with patch.dict("sys.modules", {"psycopg": None}):
            # Force ImportError for psycopg
            import sys

            saved = sys.modules.get("psycopg")
            sys.modules["psycopg"] = None  # type: ignore[assignment]
            clear_strategy_cache()
            try:
                strategy = get_prepare_strategy(conn)
                assert isinstance(strategy, NoPrepareStrategy)
            finally:
                if saved is not None:
                    sys.modules["psycopg"] = saved
                else:
                    sys.modules.pop("psycopg", None)
        get_config.cache_clear()

    def test_postgresql_with_psycopg3_returns_psycopg_strategy(self, settings):
        """PostgreSQL with psycopg3 returns PsycopgPrepareStrategy."""
        settings.QUERY_DOCTOR = {"TURBO": {"ENABLED": True}}
        from query_doctor.conf import get_config

        get_config.cache_clear()

        conn = MagicMock()
        conn.vendor = "postgresql"

        mock_psycopg = MagicMock()
        with patch.dict("sys.modules", {"psycopg": mock_psycopg}):
            clear_strategy_cache()
            strategy = get_prepare_strategy(conn)
            assert isinstance(strategy, PsycopgPrepareStrategy)
        get_config.cache_clear()

    def test_oracle_returns_implicit_cache_strategy(self, settings):
        """Oracle backend returns OracleImplicitCacheStrategy."""
        settings.QUERY_DOCTOR = {"TURBO": {"ENABLED": True}}
        from query_doctor.conf import get_config

        get_config.cache_clear()

        conn = MagicMock()
        conn.vendor = "oracle"

        strategy = get_prepare_strategy(conn)
        assert isinstance(strategy, OracleImplicitCacheStrategy)
        get_config.cache_clear()

    def test_strategy_caching_same_vendor(self, settings):
        """Same vendor returns the same cached strategy object."""
        settings.QUERY_DOCTOR = {"TURBO": {"ENABLED": True}}
        from query_doctor.conf import get_config

        get_config.cache_clear()

        conn1 = MagicMock()
        conn1.vendor = "sqlite"
        conn2 = MagicMock()
        conn2.vendor = "sqlite"

        s1 = get_prepare_strategy(conn1)
        s2 = get_prepare_strategy(conn2)

        assert s1 is s2
        get_config.cache_clear()

    def test_prepare_disabled_returns_no_prepare(self, settings):
        """PREPARE_ENABLED=False always returns NoPrepareStrategy."""
        settings.QUERY_DOCTOR = {"TURBO": {"ENABLED": True, "PREPARE_ENABLED": False}}
        from query_doctor.conf import get_config

        get_config.cache_clear()
        clear_strategy_cache()

        conn = MagicMock()
        conn.vendor = "oracle"  # Would normally get Oracle strategy

        strategy = get_prepare_strategy(conn)
        assert isinstance(strategy, NoPrepareStrategy)
        get_config.cache_clear()

    def test_custom_threshold_from_config(self, settings):
        """PREPARE_THRESHOLD from config is passed to PsycopgPrepareStrategy."""
        settings.QUERY_DOCTOR = {"TURBO": {"ENABLED": True, "PREPARE_THRESHOLD": 10}}
        from query_doctor.conf import get_config

        get_config.cache_clear()
        clear_strategy_cache()

        conn = MagicMock()
        conn.vendor = "postgresql"

        mock_psycopg = MagicMock()
        with patch.dict("sys.modules", {"psycopg": mock_psycopg}):
            strategy = get_prepare_strategy(conn)
            assert isinstance(strategy, PsycopgPrepareStrategy)
            assert strategy._threshold == 10
        get_config.cache_clear()


class TestMockPreparedExecution:
    """Mock-based tests verifying prepare=True is passed after threshold."""

    def test_prepare_true_passed_after_threshold(self):
        """After threshold hits, cursor gets prepare=True."""
        strategy = PsycopgPrepareStrategy(threshold=3)
        cursor = MagicMock()

        # Below threshold — no prepare
        assert strategy.should_prepare(2) is False
        strategy.execute(cursor, "SELECT 1", (), prepare=False)
        cursor.execute.assert_called_with("SELECT 1", ())

        # At threshold — prepare
        assert strategy.should_prepare(3) is True
        cursor.reset_mock()
        strategy.execute(cursor, "SELECT 1", (), prepare=True)
        cursor.execute.assert_called_with("SELECT 1", (), prepare=True)

    def test_graceful_fallback_preserves_result(self):
        """On fallback from TypeError, the query still executes successfully."""
        strategy = PsycopgPrepareStrategy(threshold=1)
        cursor = MagicMock()

        # First call raises TypeError, second (fallback) succeeds
        cursor.execute.side_effect = [TypeError("nope"), None]

        # Should not raise
        strategy.execute(cursor, "SELECT * FROM t WHERE id = %s", (42,), prepare=True)

        # Verify fallback call was made
        assert cursor.execute.call_count == 2
        # Last call should be without prepare
        cursor.execute.assert_called_with("SELECT * FROM t WHERE id = %s", (42,))
