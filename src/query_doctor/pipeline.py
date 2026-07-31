"""Consolidated analysis pipeline shared by every dispatch surface.

Every surface that turns captured queries into prescriptions -- the middleware,
the management commands, the pytest plugin, the ``diagnose_queries`` context
manager, the Celery integration and the project diagnoser -- routes through
``analyze()`` so analyzer discovery and ``.queryignore`` filtering behave
identically everywhere (FOLLOWUPS entry 4).

Key invariant: the analyzer input is never filtered. ``discover_analyzers()``
runs over the full, unfiltered query list; ``.queryignore`` suppresses findings
afterward, at the prescription level. Withholding queries from the analyzers was
measured to re-attribute and silently downgrade aggregate findings (see the S4
plan section 2), so it is not done here. Measurements such as
``total_queries`` therefore stay truthful regardless of ignore rules.
"""

from __future__ import annotations

import logging

from query_doctor.plugin_api import discover_analyzers
from query_doctor.types import CapturedQuery, IssueType, Prescription

logger = logging.getLogger("query_doctor")

# Prescriptions are not independent: applying one changes what another
# measures. The clearest case is that resolving an N+1 with select_related
# widens the base query, so fat_select's column count goes up as a direct
# result of doing the right thing. Reporting them in apply order stops a
# reader working the list top to bottom from chasing a number that the
# previous fix moved. Anything unlisted sorts between the two ends.
_APPLY_ORDER: dict[IssueType, int] = {
    IssueType.N_PLUS_ONE: 0,
    IssueType.WRITE_N_PLUS_ONE: 0,
    IssueType.DUPLICATE_QUERY: 1,
    IssueType.SERIALIZER_METHOD_FIELD: 1,
    IssueType.DRF_SERIALIZER: 1,
    IssueType.MISSING_INDEX: 2,
    IssueType.QUERYSET_EVAL: 2,
    IssueType.QUERY_COMPLEXITY: 3,
    IssueType.FAT_SELECT: 4,
}
_DEFAULT_APPLY_ORDER = 2


def sort_by_apply_order(prescriptions: list[Prescription]) -> list[Prescription]:
    """Order prescriptions so that applying them in sequence is stable.

    A findings list is not a set of independent items. Fixing an N+1 raises
    the column count fat_select reports for the base query, so fat_select is
    only meaningful once the N+1 findings above it are resolved.

    The sort is stable, so the order analyzers produced is preserved inside
    each rank.

    Args:
        prescriptions: The prescriptions to order.

    Returns:
        A new list in the order the fixes should be applied.
    """
    return sorted(
        prescriptions,
        key=lambda p: _APPLY_ORDER.get(p.issue_type, _DEFAULT_APPLY_ORDER),
    )


def analyze(queries: list[CapturedQuery], *, source: str) -> list[Prescription]:
    """Run every analyzer over ``queries`` and apply ``.queryignore`` filtering.

    Runs ``discover_analyzers()`` over the unfiltered query list (each analyzer
    self-gates via ``is_enabled()``), then filters the resulting prescriptions
    through the loaded ``.queryignore`` rules, passing the queries so ``sql:``
    rules can match the raw SQL behind each prescription.

    Never raises: analyzer and filtering failures are logged and skipped so the
    calling surface proceeds normally.

    Args:
        queries: The captured queries to analyze. Never mutated or filtered.
        source: Names the calling surface (e.g. ``"middleware"``); used only in
            log messages to attribute failures.

    Returns:
        The prescriptions that survived ``.queryignore`` filtering, in the
        order they should be applied (see ``sort_by_apply_order``).
    """
    prescriptions: list[Prescription] = []

    for analyzer in discover_analyzers():
        try:
            prescriptions.extend(analyzer.analyze(queries))
        except Exception:
            logger.warning(
                "query_doctor: analyzer %s failed (%s)",
                getattr(analyzer, "name", "unknown"),
                source,
                exc_info=True,
            )

    try:
        from query_doctor.ignore import filter_prescriptions, load_queryignore

        rules = load_queryignore()
        if rules:
            prescriptions = filter_prescriptions(prescriptions, rules, queries)
    except Exception:
        logger.warning("query_doctor: queryignore filtering failed (%s)", source, exc_info=True)

    return sort_by_apply_order(prescriptions)
