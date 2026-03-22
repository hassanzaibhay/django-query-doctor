"""Collectable statistics for the QueryTurbo benchmark dashboard.

Provides TurboStats which takes point-in-time snapshots of cache
performance for rendering in the HTML dashboard report.
"""

from __future__ import annotations

import time
from typing import Any

from query_doctor.turbo.cache import SQLCompilationCache


class TurboStats:
    """Collectable statistics for the benchmark dashboard.

    Takes snapshots of the SQLCompilationCache state for rendering
    in reports and dashboards.
    """

    def snapshot(self, cache: SQLCompilationCache) -> dict[str, Any]:
        """Take a point-in-time snapshot of cache performance.

        Thread-safe: acquires the cache lock to read consistent state.

        Args:
            cache: The SQLCompilationCache instance to snapshot.

        Returns:
            Dictionary with all dashboard-relevant statistics.
        """
        stats = cache.stats()

        total = stats.hits + stats.misses
        hit_rate = stats.hits / max(1, total)

        top_queries = self._get_top_queries(cache, n=20)
        prepare_stats = self._get_prepare_stats(top_queries)

        return {
            "timestamp": time.time(),
            "total_hits": stats.hits,
            "total_misses": stats.misses,
            "hit_rate": hit_rate,
            "cache_size": stats.size,
            "max_size": stats.max_size,
            "evictions": stats.evictions,
            "trusted_entries": stats.trusted_entries,
            "poisoned_entries": stats.poisoned_entries,
            "trusted_hits": stats.trusted_hits,
            "top_queries": top_queries,
            "prepare_stats": prepare_stats,
        }

    def _get_top_queries(self, cache: SQLCompilationCache, n: int = 20) -> list[dict[str, Any]]:
        """Get top N queries by hit count.

        Uses the public get_entries_snapshot() method to avoid accessing
        private cache internals.

        Args:
            cache: The cache instance.
            n: Maximum number of entries to return.

        Returns:
            List of query info dicts sorted by hit_count descending.
        """
        entries = sorted(
            [
                {
                    "sql_preview": entry.sql[:200],
                    "hit_count": entry.hit_count,
                    "trusted": entry.trusted,
                    "poisoned": entry.poisoned,
                    "model_label": entry.model_label,
                }
                for entry in cache.get_entries_snapshot()
            ],
            key=lambda e: e["hit_count"] if isinstance(e["hit_count"], int) else 0,
            reverse=True,
        )[:n]

        return entries

    def _get_prepare_stats(self, top_queries: list[dict[str, Any]]) -> dict[str, Any]:
        """Compute prepare statistics from the top queries.

        Args:
            top_queries: The top queries list.

        Returns:
            Dictionary with prepared/unprepared counts.
        """
        prepared = sum(1 for q in top_queries if q.get("is_prepared", False))
        unprepared = len(top_queries) - prepared

        return {
            "prepared_count": prepared,
            "unprepared_count": unprepared,
        }
