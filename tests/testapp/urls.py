"""URL configuration for the test app."""

from __future__ import annotations

from django.urls import path

from tests.testapp import views

urlpatterns = [
    path("books/nplusone/", views.book_list_nplusone, name="books-nplusone"),
    path("books/duplicate/", views.book_list_duplicate, name="books-duplicate"),
    path("books/optimized/", views.book_list_optimized, name="books-optimized"),
    path("books/missing-index/", views.book_list_missing_index, name="books-missing-index"),
    path("async/ok/", views.async_ok, name="async-ok"),
    path("sync/probe/", views.sync_probe, name="sync-probe"),
    path("async/probe/", views.async_probe, name="async-probe"),
    path(
        "async/probe/thread-insensitive/",
        views.async_probe_thread_insensitive,
        name="async-probe-thread-insensitive",
    ),
    path("async/burst/<int:count>/", views.query_burst, name="async-burst"),
    path("async/orm/acreate/", views.async_orm_acreate, name="async-orm-acreate"),
    path("async/orm/aget/", views.async_orm_aget, name="async-orm-aget"),
    path("async/orm/acount/", views.async_orm_acount, name="async-orm-acount"),
    path("async/orm/aexists/", views.async_orm_aexists, name="async-orm-aexists"),
    path("async/orm/aiter/", views.async_orm_aiter, name="async-orm-aiter"),
]
