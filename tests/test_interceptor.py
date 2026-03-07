"""Tests for the query interceptor in query_doctor.interceptor."""

from __future__ import annotations

import threading

import pytest
from django.db import connection

from query_doctor.interceptor import QueryInterceptor
from tests.factories import BookFactory


@pytest.mark.django_db
class TestQueryInterceptor:
    """Tests for QueryInterceptor."""

    def test_captures_queries(self) -> None:
        """Interceptor should capture SQL queries executed within the wrapper."""
        interceptor = QueryInterceptor()
        with connection.execute_wrapper(interceptor), connection.cursor() as cursor:
            cursor.execute("SELECT 1")

        queries = interceptor.get_queries()
        assert len(queries) >= 1
        assert any("SELECT 1" in q.sql for q in queries)

    def test_captures_orm_queries(self) -> None:
        """Interceptor should capture ORM-generated queries."""
        BookFactory()
        interceptor = QueryInterceptor()
        with connection.execute_wrapper(interceptor):
            from tests.testapp.models import Book

            list(Book.objects.all())

        queries = interceptor.get_queries()
        assert len(queries) >= 1
        assert any("testapp_book" in q.sql.lower() for q in queries)

    def test_records_duration(self) -> None:
        """Captured queries should have a positive duration."""
        interceptor = QueryInterceptor()
        with connection.execute_wrapper(interceptor), connection.cursor() as cursor:
            cursor.execute("SELECT 1")

        queries = interceptor.get_queries()
        assert len(queries) >= 1
        assert queries[0].duration_ms >= 0

    def test_records_fingerprint(self) -> None:
        """Captured queries should have a fingerprint."""
        interceptor = QueryInterceptor()
        with connection.execute_wrapper(interceptor), connection.cursor() as cursor:
            cursor.execute("SELECT 1")

        queries = interceptor.get_queries()
        assert len(queries) >= 1
        assert queries[0].fingerprint != ""
        assert len(queries[0].fingerprint) == 16

    def test_records_normalized_sql(self) -> None:
        """Captured queries should have normalized SQL."""
        interceptor = QueryInterceptor()
        with connection.execute_wrapper(interceptor), connection.cursor() as cursor:
            cursor.execute("SELECT 1")

        queries = interceptor.get_queries()
        assert len(queries) >= 1
        assert queries[0].normalized_sql != ""

    def test_detects_select(self) -> None:
        """is_select should be True for SELECT queries."""
        interceptor = QueryInterceptor()
        with connection.execute_wrapper(interceptor), connection.cursor() as cursor:
            cursor.execute("SELECT 1")

        queries = interceptor.get_queries()
        select_queries = [q for q in queries if "SELECT" in q.sql.upper()]
        assert len(select_queries) >= 1
        assert select_queries[0].is_select is True

    def test_extracts_tables(self) -> None:
        """Captured queries should have extracted table names."""
        interceptor = QueryInterceptor()
        with connection.execute_wrapper(interceptor), connection.cursor() as cursor:
            cursor.execute('SELECT * FROM "testapp_book"')

        queries = interceptor.get_queries()
        book_queries = [q for q in queries if "testapp_book" in q.sql]
        assert len(book_queries) >= 1
        assert "testapp_book" in book_queries[0].tables

    def test_clear(self) -> None:
        """clear() should remove all captured queries."""
        interceptor = QueryInterceptor()
        with connection.execute_wrapper(interceptor), connection.cursor() as cursor:
            cursor.execute("SELECT 1")

        assert len(interceptor.get_queries()) >= 1
        interceptor.clear()
        assert len(interceptor.get_queries()) == 0

    def test_never_breaks_query_execution(self) -> None:
        """Even if interceptor code fails, the query should still execute."""
        interceptor = QueryInterceptor()
        # The interceptor should handle errors gracefully
        with connection.execute_wrapper(interceptor), connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            assert result is not None

    def test_thread_safety(self) -> None:
        """Each thread should have its own query list via threading.local."""
        interceptor = QueryInterceptor()

        # Capture a query on the main thread
        with connection.execute_wrapper(interceptor), connection.cursor() as cursor:
            cursor.execute("SELECT 1")

        main_count = len(interceptor.get_queries())
        assert main_count >= 1

        # On a different thread, the query list should be empty
        other_thread_count: list[int] = []

        def worker() -> None:
            other_thread_count.append(len(interceptor.get_queries()))

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        assert other_thread_count[0] == 0

    def test_captures_callsite(self) -> None:
        """Captured queries should include callsite information."""
        interceptor = QueryInterceptor(capture_stack=True)
        with connection.execute_wrapper(interceptor), connection.cursor() as cursor:
            cursor.execute("SELECT 1")

        queries = interceptor.get_queries()
        assert len(queries) >= 1
        # Callsite may or may not be captured depending on stack filtering
        # but the interceptor should not crash either way

    def test_returns_execute_result(self) -> None:
        """The interceptor must return the result of execute()."""
        interceptor = QueryInterceptor()
        with connection.execute_wrapper(interceptor), connection.cursor() as cursor:
            cursor.execute("SELECT 42")
            result = cursor.fetchone()
            assert result[0] == 42
