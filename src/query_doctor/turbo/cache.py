"""Thread-safe LRU cache for compiled SQL templates.

Stores compiled (sql_template, param_positions) keyed by structural fingerprints.
Uses threading.Lock for mutation safety and collections.OrderedDict for LRU eviction.
Each entry tracks a hit_count for prepared statement threshold decisions.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, NamedTuple


@dataclass
class CacheEntry:
    """A cached SQL compilation result with hit tracking.

    Attributes:
        sql: The compiled SQL template string.
        params: The parameter tuple from the original compilation.
        hit_count: Number of times this entry has been retrieved from cache.
    """

    sql: str
    params: tuple[Any, ...]
    hit_count: int = field(default=0)


class CacheStats(NamedTuple):
    """Statistics for the SQL compilation cache.

    Attributes:
        hits: Number of cache hits.
        misses: Number of cache misses.
        size: Current number of entries in the cache.
        max_size: Maximum capacity of the cache.
        evictions: Number of entries evicted due to capacity.
    """

    hits: int
    misses: int
    size: int
    max_size: int
    evictions: int


class SQLCompilationCache:
    """Thread-safe LRU cache for compiled SQL templates.

    Stores the SQL string returned by as_sql() keyed by the structural
    fingerprint of the Query tree. On cache hit, the cached SQL template
    is reused — only fresh parameters need to be extracted.

    The cache is shared across threads within a single process.
    All mutations are protected by a threading.Lock.
    """

    def __init__(self, max_size: int = 1024) -> None:
        """Initialize the cache.

        Args:
            max_size: Maximum number of entries. Oldest entries are evicted
                      when this limit is reached.
        """
        self._max_size = max_size
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get(self, fingerprint: str) -> CacheEntry | None:
        """Look up a cached SQL template by fingerprint.

        On hit, moves the entry to the end (most recently used) and
        increments the entry's hit_count.
        Thread-safe for concurrent reads.

        Args:
            fingerprint: The blake2b hex digest of the query structure.

        Returns:
            The CacheEntry if found, None otherwise.
        """
        with self._lock:
            entry = self._cache.get(fingerprint)
            if entry is not None:
                self._hits += 1
                entry.hit_count += 1
                self._cache.move_to_end(fingerprint)
                return entry
            self._misses += 1
            return None

    def put(self, fingerprint: str, sql: str, params: tuple[Any, ...]) -> None:
        """Store a compiled SQL template in the cache.

        If the cache is at capacity, the least recently used entry is evicted.
        Thread-safe for concurrent writes.

        Args:
            fingerprint: The blake2b hex digest of the query structure.
            sql: The compiled SQL template string.
            params: The parameter tuple from compilation.
        """
        with self._lock:
            if fingerprint in self._cache:
                existing = self._cache[fingerprint]
                self._cache.move_to_end(fingerprint)
                self._cache[fingerprint] = CacheEntry(
                    sql=sql, params=params, hit_count=existing.hit_count
                )
                return

            if len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)
                self._evictions += 1

            self._cache[fingerprint] = CacheEntry(sql=sql, params=params)

    def clear(self) -> None:
        """Remove all entries from the cache.

        Thread-safe. Resets hit/miss/eviction counters.
        """
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
            self._evictions = 0

    def stats(self) -> CacheStats:
        """Return current cache statistics.

        Thread-safe snapshot of hits, misses, size, max_size, and evictions.

        Returns:
            A CacheStats namedtuple.
        """
        with self._lock:
            return CacheStats(
                hits=self._hits,
                misses=self._misses,
                size=len(self._cache),
                max_size=self._max_size,
                evictions=self._evictions,
            )

    def get_entries_snapshot(self) -> list[CacheEntry]:
        """Return a snapshot of all cache entries.

        Thread-safe: acquires the lock and returns a shallow copy of all
        entries. Used by TurboStats to build dashboard data without accessing
        private attributes.

        Returns:
            List of CacheEntry objects (shallow copies of current entries).
        """
        with self._lock:
            return list(self._cache.values())

    @property
    def size(self) -> int:
        """Return the current number of entries in the cache."""
        with self._lock:
            return len(self._cache)
