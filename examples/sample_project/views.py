"""
Sample views — each one triggers a specific query anti-pattern.
"""

from django.http import JsonResponse
from django.shortcuts import render

from models import Author, Book, Publisher, Review


def book_list(request):
    """
    TRIGGERS:
    - N+1: accessing book.author.name and book.publisher.name in template
    - Missing index: ordering by published_date (no db_index)
    - Fat SELECT: fetching description (TextField) but only showing title/price
    """
    books = Book.objects.all().order_by("-published_date")
    return render(request, "books/list.html", {"books": books})


def book_detail(request, pk):
    """
    TRIGGERS:
    - Duplicate query: book.author accessed multiple times
    - QuerySet eval: using len() instead of .count()
    """
    book = Book.objects.get(pk=pk)
    reviews = book.reviews.all()

    # BUG: Duplicate — accessing book.author here and in template
    author_name = book.author.name

    # BUG: QuerySet eval — len() instead of .count()
    review_count = len(list(reviews))

    # BUG: QuerySet eval — bool() instead of .exists()
    if reviews:
        has_reviews = True
    else:
        has_reviews = False

    return render(request, "books/detail.html", {
        "book": book,
        "reviews": reviews,
        "author_name": author_name,
        "review_count": review_count,
        "has_reviews": has_reviews,
    })


def author_books(request, author_id):
    """
    TRIGGERS:
    - N+1: accessing book.publisher and book.category for each book
    - Fat SELECT: fetching all fields when only title and price needed
    """
    author = Author.objects.get(pk=author_id)
    # BUG: N+1 — no select_related for publisher, category
    books = Book.objects.filter(author=author)
    return render(request, "books/list.html", {"books": books, "author": author})


def publisher_stats(request):
    """
    TRIGGERS:
    - N+1: separate query per publisher for book count and review count
    - Duplicate query: publishers fetched multiple ways
    """
    publishers = Publisher.objects.all()
    stats = []
    for pub in publishers:
        # BUG: N+1 — separate query per publisher
        book_count = pub.books.count()
        # BUG: N+1 — another query per publisher for reviews
        review_count = Review.objects.filter(book__publisher=pub).count()
        stats.append({
            "publisher": pub.name,
            "books": book_count,
            "reviews": review_count,
        })
    return JsonResponse({"stats": stats})
