from django.urls import path

from views import author_books, book_detail, book_list, publisher_stats

urlpatterns = [
    path("", book_list, name="book-list"),
    path("books/<int:pk>/", book_detail, name="book-detail"),
    path("authors/<int:author_id>/books/", author_books, name="author-books"),
    path("publisher-stats/", publisher_stats, name="publisher-stats"),
]
