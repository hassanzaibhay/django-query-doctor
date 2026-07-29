"""Tests for context managers in query_doctor.context_managers."""

from __future__ import annotations

import asyncio
import warnings

import pytest
from asgiref.sync import sync_to_async

from query_doctor.context_managers import diagnose_queries
from query_doctor.exceptions import QueryDoctorWarning
from query_doctor.types import IssueType
from tests.factories import BookFactory


@pytest.mark.django_db
class TestDiagnoseQueries:
    """Tests for diagnose_queries() context manager."""

    def test_captures_queries(self) -> None:
        """Should capture queries executed within the context."""
        BookFactory()

        with diagnose_queries() as report:
            from tests.testapp.models import Book

            list(Book.objects.all())

        assert report.total_queries >= 1
        assert len(report.captured_queries) >= 1

    def test_reports_total_time(self) -> None:
        """Should report total query time."""
        BookFactory()

        with diagnose_queries() as report:
            from tests.testapp.models import Book

            list(Book.objects.all())

        assert report.total_time_ms >= 0

    def test_detects_nplusone(self) -> None:
        """Should detect N+1 queries within the context."""
        for _ in range(5):
            BookFactory()

        with diagnose_queries() as report:
            from tests.testapp.models import Book

            for book in Book.objects.all():
                _ = book.author.name

        assert report.issues >= 1
        assert any(p.issue_type == IssueType.N_PLUS_ONE for p in report.prescriptions)

    def test_clean_context_no_queries(self) -> None:
        """No queries in context should produce empty report."""
        with diagnose_queries() as report:
            pass  # No queries

        assert report.total_queries == 0
        assert report.issues == 0

    def test_report_available_after_context(self) -> None:
        """Report should be fully populated after context exits."""
        BookFactory()

        with diagnose_queries() as report:
            from tests.testapp.models import Book

            list(Book.objects.all())

        # Report should be usable after the context
        assert isinstance(report.total_queries, int)
        assert isinstance(report.total_time_ms, float)


class TestDiagnoseQueriesUnderAsync:
    """The context manager announces the async limitation instead of hiding it.

    ``diagnose_queries()`` installs its ``execute_wrapper`` on the calling
    thread's connection object (``context_managers.py:74-76``). Django's
    connection registry is thread-local, so a ``with`` block in an ``async def``
    body installs on the event loop thread while the ORM runs in the
    thread-sensitive executor holding a different connection -- the block
    reports zero queries however many it issued (FOLLOWUPS entry 22, measured
    ``same_thread=False same_conn=False wrappers_in_view=0``).

    The warning predicate is "a loop is running on this thread", which is exact:
    it is true only on the broken path. A ``def`` view served under ASGI and a
    ``sync_to_async``-wrapped helper both run in the executor thread, have no
    running loop, and capture correctly -- the two tests below are what keep an
    unconditional warning from passing this class.
    """

    def test_warns_when_entered_with_a_running_loop(self) -> None:
        """A ``with`` block inside a coroutine must say that it captures nothing."""

        async def coro() -> None:
            with diagnose_queries():
                pass

        with pytest.warns(QueryDoctorWarning, match="async") as record:
            asyncio.run(coro())

        attributed = [w for w in record if issubclass(w.category, QueryDoctorWarning)]
        assert len(attributed) == 1
        message = str(attributed[0].message)
        # Steering matters more than the diagnosis: a caller who reads this has
        # to learn what to use instead, not only that this does not work.
        assert "middleware" in message

    def test_no_warning_from_a_synchronous_caller(self) -> None:
        """Positive control: the ordinary sync path must stay silent.

        Without this, a ``diagnose_queries`` that warned unconditionally would
        satisfy the test above.
        """
        with warnings.catch_warnings(record=True) as record:
            warnings.simplefilter("always")
            with diagnose_queries():
                pass

        assert [w for w in record if issubclass(w.category, QueryDoctorWarning)] == []

    def test_no_warning_inside_a_sync_to_async_helper(self) -> None:
        """Second positive control: the executor thread captures, so it must not warn.

        This is the shape of a ``def`` view served under ASGI, which
        ``docs/guides/async-support.md`` documents as working. The helper body
        runs on a worker thread with no running loop even though a loop is
        running on the thread that awaited it, so a predicate that asked "is
        this program async" rather than "is a loop running on *this* thread"
        would fire here and be wrong.
        """
        captured: list[warnings.WarningMessage] = []

        def helper() -> None:
            with warnings.catch_warnings(record=True) as record:
                warnings.simplefilter("always")
                with diagnose_queries():
                    pass
            captured.extend(record)

        async def coro() -> None:
            await sync_to_async(helper, thread_sensitive=True)()

        asyncio.run(coro())

        assert [w for w in captured if issubclass(w.category, QueryDoctorWarning)] == []
