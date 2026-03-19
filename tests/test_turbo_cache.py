"""Tests for SQLCompilationCache operations, LRU eviction, and thread safety."""

from __future__ import annotations

import threading

from query_doctor.turbo.cache import SQLCompilationCache


class TestCacheBasicOperations:
    """Basic get/put/clear operations."""

    def test_put_and_get(self):
        """Cache stores and retrieves entries correctly."""
        cache = SQLCompilationCache(max_size=10)
        cache.put("fp1", "SELECT * FROM books WHERE id = %s", (1,))

        entry = cache.get("fp1")
        assert entry is not None
        assert entry.sql == "SELECT * FROM books WHERE id = %s"
        assert entry.params == (1,)

    def test_get_miss(self):
        """Cache returns None for missing entries."""
        cache = SQLCompilationCache(max_size=10)
        assert cache.get("nonexistent") is None

    def test_clear(self):
        """Clear removes all entries and resets stats."""
        cache = SQLCompilationCache(max_size=10)
        cache.put("fp1", "SELECT 1", ())
        cache.put("fp2", "SELECT 2", ())
        cache.get("fp1")  # hit
        cache.get("missing")  # miss

        cache.clear()

        assert cache.size == 0
        stats = cache.stats()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.evictions == 0

    def test_overwrite_existing_key(self):
        """Putting same key updates the entry."""
        cache = SQLCompilationCache(max_size=10)
        cache.put("fp1", "SELECT 1", ())
        cache.put("fp1", "SELECT 2", ())

        entry = cache.get("fp1")
        assert entry is not None
        assert entry.sql == "SELECT 2"
        assert cache.size == 1


class TestCacheStats:
    """Cache statistics tracking."""

    def test_hit_tracking(self):
        """Hits are counted correctly."""
        cache = SQLCompilationCache(max_size=10)
        cache.put("fp1", "SELECT 1", ())

        cache.get("fp1")
        cache.get("fp1")

        stats = cache.stats()
        assert stats.hits == 2
        assert stats.misses == 0

    def test_miss_tracking(self):
        """Misses are counted correctly."""
        cache = SQLCompilationCache(max_size=10)

        cache.get("fp1")
        cache.get("fp2")

        stats = cache.stats()
        assert stats.hits == 0
        assert stats.misses == 2

    def test_size_tracking(self):
        """Size and max_size are reported correctly."""
        cache = SQLCompilationCache(max_size=5)
        cache.put("fp1", "SELECT 1", ())
        cache.put("fp2", "SELECT 2", ())

        stats = cache.stats()
        assert stats.size == 2
        assert stats.max_size == 5


class TestCacheLRUEviction:
    """LRU eviction behavior."""

    def test_eviction_at_capacity(self):
        """Oldest entry is evicted when cache reaches max_size."""
        cache = SQLCompilationCache(max_size=3)
        cache.put("fp1", "SELECT 1", ())
        cache.put("fp2", "SELECT 2", ())
        cache.put("fp3", "SELECT 3", ())

        # This should evict fp1
        cache.put("fp4", "SELECT 4", ())

        assert cache.get("fp1") is None
        assert cache.get("fp2") is not None
        assert cache.get("fp4") is not None
        assert cache.size == 3

    def test_eviction_count(self):
        """Eviction counter tracks correctly."""
        cache = SQLCompilationCache(max_size=2)
        cache.put("fp1", "SELECT 1", ())
        cache.put("fp2", "SELECT 2", ())
        cache.put("fp3", "SELECT 3", ())  # evicts fp1
        cache.put("fp4", "SELECT 4", ())  # evicts fp2

        stats = cache.stats()
        assert stats.evictions == 2

    def test_access_refreshes_lru(self):
        """Accessing an entry moves it to most-recently-used."""
        cache = SQLCompilationCache(max_size=3)
        cache.put("fp1", "SELECT 1", ())
        cache.put("fp2", "SELECT 2", ())
        cache.put("fp3", "SELECT 3", ())

        # Access fp1 to make it most recently used
        cache.get("fp1")

        # This should evict fp2 (oldest after fp1 was refreshed)
        cache.put("fp4", "SELECT 4", ())

        assert cache.get("fp1") is not None  # refreshed, should survive
        assert cache.get("fp2") is None  # should be evicted
        assert cache.get("fp3") is not None
        assert cache.get("fp4") is not None

    def test_max_size_one(self):
        """Cache with max_size=1 keeps only the latest entry."""
        cache = SQLCompilationCache(max_size=1)
        cache.put("fp1", "SELECT 1", ())
        cache.put("fp2", "SELECT 2", ())

        assert cache.get("fp1") is None
        assert cache.get("fp2") is not None
        assert cache.size == 1


class TestCacheThreadSafety:
    """Thread safety under concurrent access."""

    def test_concurrent_puts(self):
        """Multiple threads writing concurrently don't corrupt the cache."""
        cache = SQLCompilationCache(max_size=1000)
        errors: list[Exception] = []

        def writer(thread_id: int) -> None:
            try:
                for i in range(100):
                    cache.put(f"fp_{thread_id}_{i}", f"SELECT {i}", (i,))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert cache.size <= 1000

    def test_concurrent_reads_and_writes(self):
        """Mixed reads and writes don't cause errors."""
        cache = SQLCompilationCache(max_size=100)
        errors: list[Exception] = []

        # Pre-populate
        for i in range(50):
            cache.put(f"fp_{i}", f"SELECT {i}", (i,))

        def reader() -> None:
            try:
                for i in range(100):
                    cache.get(f"fp_{i % 50}")
            except Exception as e:
                errors.append(e)

        def writer() -> None:
            try:
                for i in range(100):
                    cache.put(f"fp_new_{i}", f"SELECT new {i}", (i,))
            except Exception as e:
                errors.append(e)

        threads = [
            *[threading.Thread(target=reader) for _ in range(5)],
            *[threading.Thread(target=writer) for _ in range(5)],
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert cache.size <= 100

    def test_concurrent_clear_and_access(self):
        """Clear during concurrent access doesn't cause errors."""
        cache = SQLCompilationCache(max_size=100)
        errors: list[Exception] = []

        def accessor() -> None:
            try:
                for i in range(100):
                    cache.put(f"fp_{i}", f"SELECT {i}", (i,))
                    cache.get(f"fp_{i}")
            except Exception as e:
                errors.append(e)

        def clearer() -> None:
            try:
                for _ in range(10):
                    cache.clear()
            except Exception as e:
                errors.append(e)

        threads = [
            *[threading.Thread(target=accessor) for _ in range(5)],
            threading.Thread(target=clearer),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
