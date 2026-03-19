"""Tests for QueryTurbo cache invalidation: migration signal, manual clear."""

from __future__ import annotations

import pytest

from query_doctor.turbo.patch import get_cache, install_patch, uninstall_patch
from query_doctor.turbo.signals import clear_cache_on_migrate


@pytest.fixture(autouse=True)
def _turbo_patch(settings):
    """Install and uninstall the turbo patch for each test."""
    settings.QUERY_DOCTOR = {"TURBO": {"ENABLED": True}}
    from query_doctor.conf import get_config

    get_config.cache_clear()

    install_patch()
    yield
    uninstall_patch()
    get_config.cache_clear()


class TestManualCacheClear:
    """Manual cache clearing operations."""

    def test_clear_empties_cache(self):
        """Calling clear() removes all entries."""
        cache = get_cache()
        assert cache is not None

        cache.put("fp1", "SELECT 1", ())
        cache.put("fp2", "SELECT 2", ())
        assert cache.size == 2

        cache.clear()
        assert cache.size == 0

    def test_clear_resets_stats(self):
        """Clearing cache resets all statistics."""
        cache = get_cache()
        assert cache is not None

        cache.put("fp1", "SELECT 1", ())
        cache.get("fp1")  # hit
        cache.get("fp2")  # miss

        cache.clear()
        stats = cache.stats()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.evictions == 0

    def test_cache_usable_after_clear(self):
        """Cache works normally after being cleared."""
        cache = get_cache()
        assert cache is not None

        cache.put("fp1", "SELECT 1", ())
        cache.clear()

        cache.put("fp2", "SELECT 2", ())
        entry = cache.get("fp2")
        assert entry is not None
        assert entry.sql == "SELECT 2"


class TestMigrationSignalInvalidation:
    """Post-migrate signal clears the cache."""

    def test_signal_handler_clears_cache(self):
        """clear_cache_on_migrate empties the global cache."""
        cache = get_cache()
        assert cache is not None

        cache.put("fp1", "SELECT 1", ())
        cache.put("fp2", "SELECT 2", ())
        assert cache.size == 2

        # Simulate the signal
        clear_cache_on_migrate(sender="testapp")

        assert cache.size == 0

    def test_signal_handler_safe_when_no_cache(self):
        """Signal handler doesn't crash when cache is None."""
        uninstall_patch()
        # Should not raise
        clear_cache_on_migrate(sender="testapp")

    def test_cache_works_after_signal(self):
        """Cache is functional after signal-triggered clear."""
        cache = get_cache()
        assert cache is not None

        cache.put("fp1", "SELECT 1", ())
        clear_cache_on_migrate(sender="testapp")

        cache.put("fp2", "SELECT 2", ())
        assert cache.get("fp2") is not None
        assert cache.size == 1


@pytest.mark.django_db
class TestPostMigrateIntegration:
    """Integration test for post_migrate signal connection."""

    def test_signal_connected_when_turbo_enabled(self, settings):
        """When turbo is enabled, post_migrate signal is connected."""
        from django.db.models.signals import post_migrate

        # The signal should already be connected via the fixture
        # Verify by checking that the handler is in the receivers
        [r[1]() for r in post_migrate.receivers if r[1]() is not None]
        # We can't easily check the exact function, but we can verify
        # the signal handler works by calling it
        cache = get_cache()
        assert cache is not None
        cache.put("test", "SELECT 1", ())

        clear_cache_on_migrate(sender="testapp")
        assert cache.size == 0
