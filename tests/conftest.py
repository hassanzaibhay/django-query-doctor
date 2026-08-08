"""Pytest configuration and shared helpers for the django-query-doctor suite."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from django.db import connection

from query_doctor.interceptor import QueryInterceptor
from query_doctor.types import CapturedQuery, Prescription

# Enables the ``pytester`` fixture used by the pytest-plugin integration tests
# to run an inner pytest session against our own terminal-summary hook.
pytest_plugins = ["pytester"]


def capture_queries(func: Callable[[], Any]) -> list[CapturedQuery]:
    """Run ``func`` and return the queries it issued.

    Args:
        func: A zero-argument callable that touches the ORM.

    Returns:
        Every query captured while it ran.
    """
    interceptor = QueryInterceptor()
    with connection.execute_wrapper(interceptor):
        func()
    return interceptor.get_queries()


def apply_prescription(rx: Prescription) -> None:
    """Run whatever relation a prescription names, or its bulk fetch.

    Raises whatever Django raises, which is the point: a prescription naming
    a field that does not resolve fails with Django's own FieldError or
    ValueError rather than with a string comparison that a reworded message
    would silently satisfy. A prescription naming no relation is exercised
    through its bulk-fetch advice instead, so every path ends in a real query.

    Args:
        rx: A prescription carrying ``extra["model"]`` and ``extra["strategy"]``,
            plus ``extra["field"]`` when a relation is named.
    """
    from django.apps import apps

    model = apps.get_model(rx.extra["model"])
    field = rx.extra.get("field")
    strategy = rx.extra["strategy"]
    if strategy == "select_related":
        list(model.objects.select_related(field)[:1])
    elif strategy == "prefetch_related":
        list(model.objects.prefetch_related(field)[:1])
    else:
        assert strategy == "bulk_fetch", strategy
        assert field is None
        list(model.objects.filter(pk__in=[1, 2, 3]))
