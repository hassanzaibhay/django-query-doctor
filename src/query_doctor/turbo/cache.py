"""Thread-safe LRU cache for compiled SQL templates.

Stores compiled (sql_template, param_count) keyed by structural fingerprints.
Uses threading.Lock for mutation safety and collections.OrderedDict for LRU eviction.
Each entry tracks a hit_count and a trust lifecycle for compilation skipping.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import NamedTuple


@dataclass
class CacheEntry:
    """A cached SQL compilation result with trust lifecycle tracking.

    Attributes:
        sql: The compiled SQL template string.
        param_count: Number of parameters in the SQL template.
        hit_count: Number of times this entry has been retrieved from cache.
        validated_count: Successful validations (fresh_sql == cached_sql).
        trusted: True after VALIDATION_THRESHOLD successful validations.
        poisoned: True if a fingerprint collision was detected.
        model_label: The model label for diagnostics.
    """

    sql: str
    param_count: int = 0
    hit_count: int = field(default=0)
    validated_count: int = field(default=0)
    trusted: bool = field(default=False)
    poisoned: bool = field(default=False)
    model_label: str = field(default="")


class CacheStats(NamedTuple):
    """Statistics for the SQL compilation cache.

    Attributes:
        hits: Number of cache hits.
        misses: Number of cache misses.
        size: Current number of entries in the cache.
        max_size: Maximum capacity of the cache.
        evictions: Number of entries evicted due to capacity.
        trusted_entries: Number of entries in TRUSTED state.
        poisoned_entries: Number of entries in POISONED state.
        trusted_hits: Number of cache hits that skipped as_sql().
    """

    hits: int
    misses: int
    size: int
    max_size: int
    evictions: int
    trusted_entries: int
    poisoned_entries: int
    trusted_hits: int


class SQLCompilationCache:
    """Thread-safe LRU cache for compiled SQL templates.

    Stores the SQL string returned by as_sql() keyed by the structural
    fingerprint of the Query tree. Implements a three-phase trust lifecycle:

    1. UNTRUSTED: Validates cached SQL against fresh as_sql() on each hit.
    2. TRUSTED: Skips as_sql() entirely, extracts params from Query tree.
    3. POISONED: Fingerprint collision detected, cache permanently bypassed.

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
        self._trusted_hits = 0

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

    def record_trusted_hit(self) -> None:
        """Record that a cache hit used the TRUSTED path (skipped as_sql).

        Thread-safe.
        """
        with self._lock:
            self._trusted_hits += 1

    def put(
        self,
        fingerprint: str,
        sql: str,
        param_count: int,
        model_label: str = "",
    ) -> None:
        """Store a compiled SQL template in the cache.

        If the cache is at capacity, the least recently used entry is evicted.
        Thread-safe for concurrent writes.

        Args:
            fingerprint: The blake2b hex digest of the query structure.
            sql: The compiled SQL template string.
            param_count: Number of params in the SQL template.
            model_label: The model label for diagnostics.
        """
        with self._lock:
            if fingerprint in self._cache:
                existing = self._cache[fingerprint]
                self._cache.move_to_end(fingerprint)
                self._cache[fingerprint] = CacheEntry(
                    sql=sql,
                    param_count=param_count,
                    hit_count=existing.hit_count,
                    validated_count=existing.validated_count,
                    trusted=existing.trusted,
                    poisoned=existing.poisoned,
                    model_label=model_label or existing.model_label,
                )
                return

            if len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)
                self._evictions += 1

            self._cache[fingerprint] = CacheEntry(
                sql=sql,
                param_count=param_count,
                model_label=model_label,
            )

    def evict(self, fingerprint: str) -> bool:
        """Remove a specific entry from the cache.

        Used when a fingerprint collision is detected (cached SQL doesn't
        match fresh SQL for the same fingerprint).

        Args:
            fingerprint: The blake2b hex digest to evict.

        Returns:
            True if the entry was found and removed, False otherwise.
        """
        with self._lock:
            if fingerprint in self._cache:
                del self._cache[fingerprint]
                self._evictions += 1
                return True
            return False

    def poison(self, fingerprint: str) -> None:
        """Mark a fingerprint as poisoned (collision detected).

        The entry stays in cache so we can identify it on future hits
        and skip immediately without a cache miss.

        Args:
            fingerprint: The blake2b hex digest to poison.
        """
        with self._lock:
            entry = self._cache.get(fingerprint)
            if entry is not None:
                entry.poisoned = True

    def clear(self) -> None:
        """Remove all entries from the cache.

        Thread-safe. Resets hit/miss/eviction counters.
        """
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
            self._evictions = 0
            self._trusted_hits = 0

    def stats(self) -> CacheStats:
        """Return current cache statistics.

        Thread-safe snapshot of all counters.

        Returns:
            A CacheStats namedtuple.
        """
        with self._lock:
            trusted_count = sum(1 for e in self._cache.values() if e.trusted)
            poisoned_count = sum(1 for e in self._cache.values() if e.poisoned)
            return CacheStats(
                hits=self._hits,
                misses=self._misses,
                size=len(self._cache),
                max_size=self._max_size,
                evictions=self._evictions,
                trusted_entries=trusted_count,
                poisoned_entries=poisoned_count,
                trusted_hits=self._trusted_hits,
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
