#!/usr/bin/env python
"""
Example 3: Decorators — @diagnose and @query_budget
"""

print("=" * 60)
print("Example 3: Decorators")
print("=" * 60)

print("""
from query_doctor import diagnose, query_budget
from query_doctor.exceptions import QueryBudgetError

# --- @diagnose: log query issues ---
@diagnose
def get_all_books():
    books = list(Book.objects.all())
    for book in books:
        _ = book.author.name  # N+1 — will be reported
    return books

# Calling get_all_books() prints diagnosis to stderr
books = get_all_books()


# --- @query_budget: enforce limits ---
@query_budget(max_queries=10, max_time_ms=100)
def efficient_book_list():
    return list(Book.objects.select_related('author', 'publisher').all())

# This passes — optimized query stays under budget
books = efficient_book_list()

@query_budget(max_queries=5)
def inefficient_book_list():
    books = list(Book.objects.all())
    for book in books:
        _ = book.author.name  # N+1 — will exceed budget
    return books

# This raises QueryBudgetError!
try:
    inefficient_book_list()
except QueryBudgetError as e:
    print(f"Budget exceeded: {e}")
""")
