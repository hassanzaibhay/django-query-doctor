"""Tests for configuration in query_doctor.conf."""

from __future__ import annotations

from django.test import override_settings

from query_doctor.conf import get_config


class TestGetConfig:
    """Tests for get_config()."""

    def test_returns_defaults(self) -> None:
        """With empty QUERY_DOCTOR setting, all defaults should be present."""
        config = get_config()
        assert config["ENABLED"] is True
        assert config["SAMPLE_RATE"] == 1.0
        assert config["CAPTURE_STACK_TRACES"] is True
        assert config["STACK_TRACE_EXCLUDE"] == []
        assert config["REPORTERS"] == ["console"]

    def test_analyzer_defaults(self) -> None:
        """Default analyzer config should be present."""
        config = get_config()
        assert config["ANALYZERS"]["nplusone"]["enabled"] is True
        assert config["ANALYZERS"]["nplusone"]["threshold"] == 3
        assert config["ANALYZERS"]["duplicate"]["enabled"] is True
        assert config["ANALYZERS"]["duplicate"]["threshold"] == 2

    def test_query_budget_defaults(self) -> None:
        """Default query budget should have None values."""
        config = get_config()
        assert config["QUERY_BUDGET"]["DEFAULT_MAX_QUERIES"] is None
        assert config["QUERY_BUDGET"]["DEFAULT_MAX_TIME_MS"] is None

    @override_settings(QUERY_DOCTOR={"ENABLED": False})
    def test_user_override_simple(self) -> None:
        """User settings should override defaults."""
        get_config.cache_clear()
        config = get_config()
        assert config["ENABLED"] is False
        # Other defaults should still be present
        assert config["SAMPLE_RATE"] == 1.0
        get_config.cache_clear()

    @override_settings(QUERY_DOCTOR={"ANALYZERS": {"nplusone": {"threshold": 5}}})
    def test_deep_merge(self) -> None:
        """Nested dicts should be deep-merged, not replaced."""
        get_config.cache_clear()
        config = get_config()
        # User overrode nplusone threshold
        assert config["ANALYZERS"]["nplusone"]["threshold"] == 5
        # But nplusone.enabled should still have its default
        assert config["ANALYZERS"]["nplusone"]["enabled"] is True
        # And duplicate analyzer should still be present
        assert config["ANALYZERS"]["duplicate"]["enabled"] is True
        get_config.cache_clear()

    @override_settings(QUERY_DOCTOR={"SAMPLE_RATE": 0.5})
    def test_partial_override(self) -> None:
        """Only the specified keys should be overridden."""
        get_config.cache_clear()
        config = get_config()
        assert config["SAMPLE_RATE"] == 0.5
        assert config["ENABLED"] is True
        get_config.cache_clear()

    def test_config_is_cached(self) -> None:
        """Repeated calls should return the same object (cached)."""
        config1 = get_config()
        config2 = get_config()
        assert config1 is config2

    @override_settings(QUERY_DOCTOR={"IGNORE_URLS": ["/admin/", "/health/"]})
    def test_ignore_urls(self) -> None:
        """IGNORE_URLS should be configurable."""
        get_config.cache_clear()
        config = get_config()
        assert config["IGNORE_URLS"] == ["/admin/", "/health/"]
        get_config.cache_clear()

    def test_missing_setting_uses_defaults(self) -> None:
        """If QUERY_DOCTOR is not set at all, defaults should be used."""
        config = get_config()
        assert config["ENABLED"] is True
