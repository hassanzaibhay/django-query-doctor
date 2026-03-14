"""Test views that trigger query patterns for integration testing."""

from __future__ import annotations

from django.http import JsonResponse

from tests.testapp.models import Book


def book_list_nplusone(request):
    """View that triggers N+1 queries by accessing author on each book."""
    books = []
    for book in Book.objects.all():
        books.append({"title": book.title, "author": book.author.name})
    return JsonResponse({"books": books})


def book_list_duplicate(request):
    """View that triggers duplicate queries by repeating the same query."""
    first = list(Book.objects.all().values_list("title", flat=True))
    second = list(Book.objects.all().values_list("title", flat=True))
    return JsonResponse({"first": first, "second": second})


def book_list_optimized(request):
    """View with optimized queries using select_related."""
    books = []
    for book in Book.objects.select_related("author").all():
        books.append({"title": book.title, "author": book.author.name})
    return JsonResponse({"books": books})
