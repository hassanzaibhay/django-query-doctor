"""Benchmark scenarios for measuring QueryTurbo performance.

Each scenario defines a query pattern, description, and iteration count.
The benchmark runner executes each scenario with and without QueryTurbo
to measure the speedup.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Avg, Count, Q


def get_scenarios() -> dict[str, dict[str, Any]]:
    """Return all benchmark scenarios.

    Scenarios are returned as callables to avoid import-time model access.

    Returns:
        Dictionary mapping scenario names to config dicts.
    """
    from benchmarks.models import Author, Book, Review

    return {
        "simple_filter": {
            "description": "Single table, single filter",
            "query": lambda: Book.objects.filter(is_active=True),
            "iterations": 10000,
        },
        "multi_filter": {
            "description": "Single table, multiple filters",
            "query": lambda: Book.objects.filter(is_active=True, price__gte=10),
            "iterations": 10000,
        },
        "select_related": {
            "description": "Two JOINs via select_related",
            "query": lambda: Book.objects.select_related("author", "publisher").filter(
                is_active=True
            ),
            "iterations": 5000,
        },
        "deep_select_related": {
            "description": "Three-level JOIN chain",
            "query": lambda: Review.objects.select_related(
                "book", "book__author", "book__publisher"
            ).filter(rating__gte=4),
            "iterations": 5000,
        },
        "annotate": {
            "description": "Annotation with Count",
            "query": lambda: Author.objects.annotate(book_count=Count("books")).filter(
                book_count__gte=1
            ),
            "iterations": 5000,
        },
        "complex": {
            "description": "JOINs + annotation + Q objects + ordering",
            "query": lambda: Book.objects.select_related("author", "publisher")
            .annotate(
                review_count=Count("reviews"),
                avg_rating=Avg("reviews__rating"),
            )
            .filter(Q(is_active=True) | Q(price__gte=50))
            .order_by("-avg_rating", "title"),
            "iterations": 2000,
        },
    }
