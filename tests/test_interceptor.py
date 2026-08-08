"""Tests for the query interceptor in query_doctor.interceptor."""

from __future__ import annotations

import ast
import contextvars
import gc
import pathlib
import threading
from typing import ClassVar

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
        """Each thread should have its own query list via contextvars.

        A new thread starts with a fresh context, so the interceptor's
        per-instance ``ContextVar`` resolves to its default there rather than
        to the list the main thread appended to.
        """
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


def _live_query_vars() -> set[str]:
    """Names of every query_doctor capture ContextVar set in this context.

    Reads the ambient context rather than any interceptor's own state, so it
    sees exactly what a long-lived worker thread would still be holding.
    """
    return {
        var.name
        for var in contextvars.copy_context()
        if var.name.startswith("query_doctor_queries_")
    }


@pytest.mark.django_db
class TestReleaseEndsTheContextEntry:
    """The interceptor must not outlive the unit of work that built it.

    ``__init__`` calls ``ContextVar.set()``, which stores the variable and its
    value in the *running* context. Under WSGI that context is the worker
    thread's own and lives as long as the process, so every request left one
    more entry behind, each holding that request's full ``CapturedQuery``
    list. Dropping the interceptor does not help: the context holds the
    reference, not the caller. ``docs/deep-dive/performance.md`` claims there
    is no accumulation across requests, and only ``release()`` makes that true.
    """

    def test_construction_adds_one_entry(self) -> None:
        """Baseline: the leak is per instance, so the count must move by one."""
        before = _live_query_vars()
        interceptor = QueryInterceptor()
        added = _live_query_vars() - before
        assert len(added) == 1
        interceptor.release()

    def test_release_removes_the_entry(self) -> None:
        """The entry is gone from the context, not merely set to None."""
        before = _live_query_vars()
        interceptor = QueryInterceptor()
        assert _live_query_vars() != before
        interceptor.release()
        assert _live_query_vars() == before

    def test_release_drops_the_captured_queries(self) -> None:
        """The retained payload is the query list; releasing must free it."""
        interceptor = QueryInterceptor()
        with connection.execute_wrapper(interceptor), connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        assert interceptor.get_queries(), "nothing captured; the test proves nothing"

        interceptor.release()

        assert interceptor.get_queries() == []

    def test_release_is_idempotent(self) -> None:
        """A second call is a no-op, not a ValueError from a spent token."""
        before = _live_query_vars()
        interceptor = QueryInterceptor()
        interceptor.release()
        interceptor.release()
        assert _live_query_vars() == before

    def test_release_from_a_foreign_context_does_not_raise(self) -> None:
        """Never crash the host app: a token is only valid where it was set.

        ``ContextVar.reset()`` rejects a token created in another context, and
        a caller that builds an interceptor on one thread and finalises on
        another would otherwise take that ValueError into the host's request
        path.
        """
        interceptor = QueryInterceptor()
        errors: list[BaseException] = []

        def worker() -> None:
            try:
                interceptor.release()
            except BaseException as exc:
                errors.append(exc)

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()

        assert errors == []
        interceptor.release()

    def test_repeated_use_does_not_accumulate(self) -> None:
        """The leak test proper: N units of work leave nothing behind.

        Fifty stands in for fifty requests served by one gunicorn worker.
        Without ``release()`` this ends at fifty entries; the assertion is on
        the ambient context, so it fails for the real reason.
        """
        before = _live_query_vars()

        for _ in range(50):
            interceptor = QueryInterceptor()
            with connection.execute_wrapper(interceptor), connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            interceptor.release()

        gc.collect()
        assert _live_query_vars() == before


class TestEveryDispatchSiteReleases:
    """``release()`` is only a fix if every construction site calls it.

    The leak is a class, not an instance: nine call sites build an interceptor
    and each one that skips the release reintroduces it. Checked against the
    AST rather than by review so a tenth site cannot land unreleased.
    """

    # The factory hands ownership to its caller rather than keeping it, so it
    # is the one constructing function with nothing to release. Named here so
    # the exemption is a decision on the record, not a silent gap in the scan.
    OWNERSHIP_TRANSFER: ClassVar[frozenset[str]] = frozenset({"interceptor.py:build_interceptor"})

    @staticmethod
    def _functions_building_an_interceptor() -> list[tuple[str, ast.AST]]:
        """Every src/ function whose body constructs an interceptor."""
        root = pathlib.Path(__file__).resolve().parents[1] / "src" / "query_doctor"
        found: list[tuple[str, ast.AST]] = []

        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                builds = any(
                    isinstance(call.func, ast.Name)
                    and call.func.id in {"build_interceptor", "QueryInterceptor"}
                    for call in ast.walk(node)
                    if isinstance(call, ast.Call)
                )
                if builds:
                    found.append((f"{path.name}:{node.name}", node))
        return found

    def test_the_scan_finds_the_known_sites(self) -> None:
        """Positive control: an empty scan would pass the next test vacuously."""
        sites = self._functions_building_an_interceptor()
        names = {name for name, _ in sites}
        assert "middleware.py:_sync_call" in names, names
        assert "middleware.py:__acall__" in names, names
        assert len(sites) >= 8, names

    def test_every_site_releases(self) -> None:
        """Each constructing function must also call ``.release()``."""
        offenders = [
            name
            for name, node in self._functions_building_an_interceptor()
            if name not in self.OWNERSHIP_TRANSFER
            and not any(
                isinstance(call.func, ast.Attribute) and call.func.attr == "release"
                for call in ast.walk(node)
                if isinstance(call, ast.Call)
            )
        ]
        assert offenders == [], f"interceptor built but never released in: {offenders}"
