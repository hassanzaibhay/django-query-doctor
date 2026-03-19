"""Tests for QueryTurbo statistics collection."""

from __future__ import annotations

from query_doctor.turbo.cache import SQLCompilationCache
from query_doctor.turbo.stats import TurboStats


class TestTurboStats:
    """Tests for TurboStats snapshot collection."""

    def test_snapshot_empty_cache(self):
        """Snapshot of empty cache returns zero values."""
        cache = SQLCompilationCache(max_size=100)
        stats = TurboStats()

        snapshot = stats.snapshot(cache)

        assert snapshot["total_hits"] == 0
        assert snapshot["total_misses"] == 0
        assert snapshot["hit_rate"] == 0
        assert snapshot["cache_size"] == 0
        assert snapshot["max_size"] == 100
        assert snapshot["evictions"] == 0
        assert snapshot["top_queries"] == []
        assert snapshot["prepare_stats"] == {"prepared_count": 0, "unprepared_count": 0}
        assert "timestamp" in snapshot

    def test_snapshot_with_entries(self):
        """Snapshot captures cache entries and hit counts."""
        cache = SQLCompilationCache(max_size=100)
        cache.put("fp1", "SELECT 1", ())
        cache.put("fp2", "SELECT 2", ())

        # Generate some hits
        cache.get("fp1")
        cache.get("fp1")
        cache.get("fp1")
        cache.get("fp2")

        # Generate a miss
        cache.get("fp_missing")

        stats = TurboStats()
        snapshot = stats.snapshot(cache)

        assert snapshot["total_hits"] == 4
        assert snapshot["total_misses"] == 1
        assert snapshot["hit_rate"] == 4 / 5
        assert snapshot["cache_size"] == 2
        assert len(snapshot["top_queries"]) == 2

    def test_top_queries_sorted_by_hit_count(self):
        """Top queries are sorted by hit count descending."""
        cache = SQLCompilationCache(max_size=100)
        cache.put("fp1", "SELECT 1", ())
        cache.put("fp2", "SELECT 2", ())

        cache.get("fp1")
        cache.get("fp2")
        cache.get("fp2")
        cache.get("fp2")

        stats = TurboStats()
        snapshot = stats.snapshot(cache)

        top = snapshot["top_queries"]
        assert len(top) == 2
        assert top[0]["hit_count"] >= top[1]["hit_count"]
        assert top[0]["sql_preview"] == "SELECT 2"

    def test_top_queries_limited_to_n(self):
        """Top queries are limited to N entries."""
        cache = SQLCompilationCache(max_size=100)
        for i in range(30):
            cache.put(f"fp{i}", f"SELECT {i}", ())

        stats = TurboStats()
        snapshot = stats.snapshot(cache)

        assert len(snapshot["top_queries"]) <= 20

    def test_sql_preview_truncated(self):
        """SQL preview is truncated to 200 chars."""
        cache = SQLCompilationCache(max_size=100)
        long_sql = "SELECT " + "x" * 300
        cache.put("fp1", long_sql, ())

        stats = TurboStats()
        snapshot = stats.snapshot(cache)

        assert len(snapshot["top_queries"][0]["sql_preview"]) == 200

    def test_prepare_stats(self):
        """Prepare stats count prepared vs unprepared entries."""
        cache = SQLCompilationCache(max_size=100)
        cache.put("fp1", "SELECT 1", ())

        stats = TurboStats()
        snapshot = stats.snapshot(cache)

        # No entries are "prepared" since we don't set is_prepared
        ps = snapshot["prepare_stats"]
        assert ps["prepared_count"] == 0
        assert ps["unprepared_count"] == 1

    def test_hit_rate_calculation(self):
        """Hit rate is correctly calculated."""
        cache = SQLCompilationCache(max_size=100)
        cache.put("fp1", "SELECT 1", ())

        # 3 hits, 2 misses
        cache.get("fp1")
        cache.get("fp1")
        cache.get("fp1")
        cache.get("missing1")
        cache.get("missing2")

        stats = TurboStats()
        snapshot = stats.snapshot(cache)

        assert snapshot["total_hits"] == 3
        assert snapshot["total_misses"] == 2
        assert snapshot["hit_rate"] == 3 / 5
