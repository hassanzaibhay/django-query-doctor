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
        from query_doctor.analyzers.drf_serializer import DRFSerializerAnalyzer

        analyzers.append(DRFSerializerAnalyzer())
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

    return analyzers


def discover_analyzers() -> list[BaseAnalyzer]:
    """Load built-in analyzers plus any third-party plugins.

    Discovers plugins registered via the 'query_doctor.analyzers'
    entry point group. Invalid or failing plugins are logged and skipped.

    Returns:
        List of all available analyzer instances.
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

    return analyzers


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
