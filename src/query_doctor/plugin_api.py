"""Custom analyzer plugin API for django-query-doctor.

Provides a discovery system for loading third-party analyzers registered
via Python entry points. Third-party packages can register custom analyzers
by adding an entry point in their pyproject.toml:

    [project.entry-points."query_doctor.analyzers"]
    my_analyzer = "my_package.analyzers:MyCustomAnalyzer"

The custom analyzer must subclass BaseAnalyzer and implement analyze().

Usage:
    from query_doctor.plugin_api import discover_analyzers

    analyzers = discover_analyzers()  # Built-in + third-party
"""

from __future__ import annotations

import functools
import logging
from importlib.metadata import entry_points

from query_doctor.analyzers.base import BaseAnalyzer

logger = logging.getLogger("query_doctor")


def get_builtin_analyzers() -> list[BaseAnalyzer]:
    """Return instances of all built-in analyzers.

    Returns:
        List of built-in analyzer instances.
    """
    analyzers: list[BaseAnalyzer] = []

    from query_doctor.analyzers.duplicate import DuplicateAnalyzer
    from query_doctor.analyzers.nplusone import NPlusOneAnalyzer

    analyzers.append(NPlusOneAnalyzer())
    analyzers.append(DuplicateAnalyzer())

    try:
        from query_doctor.analyzers.missing_index import MissingIndexAnalyzer

        analyzers.append(MissingIndexAnalyzer())
    except Exception:
        pass

    try:
        from query_doctor.analyzers.fat_select import FatSelectAnalyzer

        analyzers.append(FatSelectAnalyzer())
    except Exception:
        pass

    try:
        from query_doctor.analyzers.queryset_eval import QuerySetEvalAnalyzer

        analyzers.append(QuerySetEvalAnalyzer())
    except Exception:
        pass

    try:
        from query_doctor.analyzers.complexity import QueryComplexityAnalyzer

        analyzers.append(QueryComplexityAnalyzer())
    except Exception:
        pass

    try:
        from query_doctor.analyzers.serializer_method import SerializerMethodAnalyzer

        analyzers.append(SerializerMethodAnalyzer())
    except Exception:
        pass

    try:
        from query_doctor.analyzers.write_nplusone import WriteNPlusOneAnalyzer

        analyzers.append(WriteNPlusOneAnalyzer())
    except Exception:
        pass

    return analyzers


@functools.lru_cache(maxsize=1)
def _discover_analyzers_cached() -> tuple[BaseAnalyzer, ...]:
    """Build the analyzer set once and hold it for the process.

    Separate from ``discover_analyzers`` only so the public function can hand
    back a fresh list per call; this is where the caching actually lives.

    Caching analyzer *instances* is safe because analyzers hold no per-run
    state: ``FatSelectAnalyzer.__init__`` sets ``_threshold_override``
    (``analyzers/fat_select.py:64``) and that is the only instance attribute
    assigned anywhere in ``analyzers/``, set once at construction and never
    mutated during ``analyze``. Configuration stays live because every analyzer
    reads ``get_config()`` at analyze time (``is_enabled()``,
    ``FatSelectAnalyzer._get_threshold``), not at construction.

    Returns:
        Tuple of all available analyzer instances.
    """
    analyzers = get_builtin_analyzers()

    try:
        plugins = _load_entry_point_analyzers()
        analyzers.extend(plugins)
    except Exception:
        logger.warning(
            "query_doctor: failed to load analyzer plugins",
            exc_info=True,
        )

    return tuple(analyzers)


def discover_analyzers() -> list[BaseAnalyzer]:
    """Load built-in analyzers plus any third-party plugins.

    Discovers plugins registered via the 'query_doctor.analyzers'
    entry point group. Invalid or failing plugins are logged and skipped.

    The entry point scan is cached for the process: ``_load_entry_point_analyzers``
    walks every installed distribution and reads its ``entry_points.txt`` from
    disk, which was measured at 87 reads per call against 87 installed
    distributions -- ~8 ms of synchronous filesystem I/O, flat in query count,
    paid by every surface routing through ``pipeline.analyze`` and once per URL
    pattern by the project diagnoser (FOLLOWUPS entry 29).

    Call ``discover_analyzers.cache_clear()`` to force a rescan. Tests that
    patch discovery must clear it, the same way ``get_config.cache_clear()`` is
    used around settings overrides; without that the patch is never consulted
    and the test passes while exercising nothing.

    A fresh list is returned per call rather than the cached container, so a
    caller appending to the result cannot corrupt later calls. The copy costs
    ~0.1 microseconds for eight analyzers.

    Returns:
        List of all available analyzer instances.
    """
    return list(_discover_analyzers_cached())


# Part of the public contract, not an implementation detail: the cache is only
# safe to introduce if callers -- tests above all -- can drop it.
discover_analyzers.cache_clear = _discover_analyzers_cached.cache_clear  # type: ignore[attr-defined]


def _load_entry_point_analyzers() -> list[BaseAnalyzer]:
    """Load analyzer plugins from entry points.

    Returns:
        List of valid analyzer instances from entry points.
    """
    loaded: list[BaseAnalyzer] = []

    eps = entry_points(group="query_doctor.analyzers")

    for ep in eps:
        try:
            analyzer_class = ep.load()
            if isinstance(analyzer_class, type) and issubclass(analyzer_class, BaseAnalyzer):
                loaded.append(analyzer_class())
            else:
                logger.warning(
                    "query_doctor: plugin %s is not a BaseAnalyzer subclass, skipping",
                    ep.name,
                )
        except Exception:
            logger.warning(
                "query_doctor: failed to load analyzer plugin %s",
                ep.name,
                exc_info=True,
            )

    return loaded
