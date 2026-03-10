"""URL configuration for the test app."""

from __future__ import annotations

from django.urls import path

from tests.testapp import views

urlpatterns = [
    path("books/nplusone/", views.book_list_nplusone, name="books-nplusone"),
    path("books/duplicate/", views.book_list_duplicate, name="books-duplicate"),
    path("books/optimized/", views.book_list_optimized, name="books-optimized"),
]
