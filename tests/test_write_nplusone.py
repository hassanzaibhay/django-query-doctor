"""Tests for write N+1 detection in query_doctor.analyzers.write_nplusone."""

from __future__ import annotations

import pytest
from django.db import connection
from django.test import override_settings

from query_doctor.analyzers.write_nplusone import WriteNPlusOneAnalyzer
from query_doctor.conf import get_config
from query_doctor.interceptor import QueryInterceptor
from query_doctor.types import CallSite, CapturedQuery, IssueType, Severity
from tests.factories import AuthorFactory, BookFactory, PublisherFactory


def _write(sql: str, count: int = 1) -> list[CapturedQuery]:
    """Build ``count`` synthetic non-SELECT captures sharing one fingerprint.

    Real captures are used wherever the test is about Django's SQL; these are
    used where the test is about the analyzer's own classification and the
    exact statement text is the input under test.
    """
    from query_doctor.fingerprint import fingerprint, normalize_sql

    normalized = normalize_sql(sql)
    return [
        CapturedQuery(
            sql=sql,
            params=None,
            duration_ms=0.5,
            fingerprint=fingerprint(sql),
            normalized_sql=normalized,
            callsite=CallSite("/app/views.py", 42, "save_all", "obj.save()"),
            is_select=False,
            tables=[],
        )
        for _ in range(count)
    ]


class TestWriteNPlusOneDetection:
    """The detection rule itself, against synthetic statements."""

    def test_repeated_inserts_prescribe_bulk_create(self) -> None:
        """Five identical INSERTs are a write N+1 fixed by bulk_create()."""
        queries = _write('INSERT INTO "testapp_book" ("title", "isbn") VALUES (%s, %s)', 5)

        prescriptions = WriteNPlusOneAnalyzer().analyze(queries)

        assert len(prescriptions) == 1
        p = prescriptions[0]
        assert p.issue_type == IssueType.WRITE_N_PLUS_ONE
        assert p.query_count == 5
        assert "bulk_create" in p.fix_suggestion
        assert p.extra["table"] == "testapp_book"
        assert p.extra["statement"] == "insert"

    def test_repeated_updates_prescribe_bulk_update(self) -> None:
        """Five identical UPDATEs are fixed by bulk_update(), not bulk_create()."""
        queries = _write('UPDATE "testapp_book" SET "title" = %s WHERE "id" = %s', 5)

        prescriptions = WriteNPlusOneAnalyzer().analyze(queries)

        assert len(prescriptions) == 1
        p = prescriptions[0]
        assert p.extra["statement"] == "update"
        assert "bulk_update" in p.fix_suggestion
        assert "bulk_create" not in p.fix_suggestion

    def test_repeated_deletes_prescribe_a_single_queryset_delete(self) -> None:
        """Five identical DELETEs are fixed by one filtered .delete()."""
        queries = _write('DELETE FROM "testapp_book" WHERE "id" = %s', 5)

        prescriptions = WriteNPlusOneAnalyzer().analyze(queries)

        assert len(prescriptions) == 1
        p = prescriptions[0]
        assert p.extra["statement"] == "delete"
        assert ".delete()" in p.fix_suggestion

    def test_transaction_control_statements_are_not_writes(self) -> None:
        """BEGIN/COMMIT/SAVEPOINT are captured as non-SELECT and must be ignored.

        Measured, not assumed: a captured ``BEGIN`` arrives with
        ``is_select=False`` and its own fingerprint, so a rule that grouped every
        non-SELECT would report a write N+1 on any request opening several
        transactions. This is the edge case that shaped the filter.
        """
        for statement in ("BEGIN", "COMMIT", "ROLLBACK", "SAVEPOINT s1", "RELEASE SAVEPOINT s1"):
            queries = _write(statement, 5)

            assert WriteNPlusOneAnalyzer().analyze(queries) == [], statement

    def test_selects_are_left_to_the_nplusone_analyzer(self) -> None:
        """Repeated SELECTs are not this analyzer's finding."""
        selects = [
            CapturedQuery(
                sql='SELECT "id" FROM "testapp_book" WHERE "author_id" = %s',
                params=None,
                duration_ms=0.5,
                fingerprint="deadbeefdeadbeef",
                normalized_sql='select "id" from "testapp_book" where "author_id" = ?',
                callsite=None,
                is_select=True,
                tables=["testapp_book"],
            )
            for _ in range(5)
        ]

        assert WriteNPlusOneAnalyzer().analyze(selects) == []

    def test_a_single_multi_row_insert_is_not_flagged(self) -> None:
        """bulk_create() emits one INSERT with many value tuples.

        The prescribed fix must not itself trip the rule.
        """
        bulk = _write(
            'INSERT INTO "testapp_book" ("title") VALUES (%s), (%s), (%s), (%s), (%s)',
            1,
        )

        assert WriteNPlusOneAnalyzer().analyze(bulk) == []

    def test_ddl_is_not_a_row_write(self) -> None:
        """Schema statements are non-SELECT but write no rows, so they must be ignored.

        Migrations issue these through the same connection, and a migration
        creating several tables would otherwise be reported as a write N+1.
        """
        for statement in (
            'CREATE TABLE "t" ("id" integer)',
            'CREATE INDEX "i" ON "t" ("id")',
            'ALTER TABLE "t" ADD COLUMN "x" integer',
            'DROP TABLE "t"',
        ):
            assert WriteNPlusOneAnalyzer().analyze(_write(statement, 5)) == [], statement

    def test_writes_to_different_tables_do_not_group(self) -> None:
        """Grouping is per statement shape, so two tables below threshold stay silent."""
        queries = _write('INSERT INTO "testapp_book" ("title") VALUES (%s)', 2)
        queries += _write('INSERT INTO "testapp_author" ("name") VALUES (%s)', 2)

        assert WriteNPlusOneAnalyzer().analyze(queries) == []


class TestWriteNPlusOneThreshold:
    """Boundary behaviour of the configured threshold."""

    def test_exactly_at_threshold_is_detected(self) -> None:
        """Default threshold is 3, and 3 writes must be reported."""
        assert get_config()["ANALYZERS"]["write_nplusone"]["threshold"] == 3

        queries = _write('INSERT INTO "testapp_book" ("title") VALUES (%s)', 3)

        assert len(WriteNPlusOneAnalyzer().analyze(queries)) == 1

    def test_one_below_threshold_is_not_detected(self) -> None:
        """Two writes are below the default threshold and must stay silent."""
        queries = _write('INSERT INTO "testapp_book" ("title") VALUES (%s)', 2)

        assert WriteNPlusOneAnalyzer().analyze(queries) == []

    @override_settings(QUERY_DOCTOR={"ANALYZERS": {"write_nplusone": {"threshold": 10}}})
    def test_threshold_is_read_from_settings(self) -> None:
        """A raised threshold suppresses a group the default would report."""
        get_config.cache_clear()
        try:
            queries = _write('INSERT INTO "testapp_book" ("title") VALUES (%s)', 5)

            assert WriteNPlusOneAnalyzer().analyze(queries) == []
        finally:
            get_config.cache_clear()

    def test_severity_escalates_at_ten_writes(self) -> None:
        """Ten or more writes is CRITICAL, fewer is WARNING -- matching NPlusOneAnalyzer."""
        assert (
            WriteNPlusOneAnalyzer().analyze(_write("INSERT INTO t (a) VALUES (%s)", 9))[0].severity
            is Severity.WARNING
        )
        assert (
            WriteNPlusOneAnalyzer()
            .analyze(_write("INSERT INTO t (a) VALUES (%s)", 10))[0]
            .severity
            is Severity.CRITICAL
        )


class TestWriteNPlusOneDisabled:
    """The analyzer honours its enabled flag."""

    @override_settings(QUERY_DOCTOR={"ANALYZERS": {"write_nplusone": {"enabled": False}}})
    def test_disabled_analyzer_returns_nothing(self) -> None:
        """Disabling the analyzer suppresses a group it would otherwise report."""
        get_config.cache_clear()
        try:
            queries = _write('INSERT INTO "testapp_book" ("title") VALUES (%s)', 5)

            assert WriteNPlusOneAnalyzer().analyze(queries) == []
        finally:
            get_config.cache_clear()


@pytest.mark.django_db
class TestWriteNPlusOneAgainstRealDjango:
    """End-to-end against SQL Django actually emits, not hand-written statements."""

    def _capture(self, func) -> list[CapturedQuery]:
        """Capture the queries a callable issues."""
        interceptor = QueryInterceptor()
        with connection.execute_wrapper(interceptor):
            func()
        return interceptor.get_queries()

    def test_create_in_a_loop_is_detected(self) -> None:
        """``Model.objects.create()`` in a loop is the canonical write N+1."""
        author = AuthorFactory()
        publisher = PublisherFactory()

        def create_in_a_loop() -> None:
            from tests.testapp.models import Book

            for i in range(4):
                Book.objects.create(
                    title=f"t{i}",
                    isbn=f"isbn-loop-{i}",
                    author=author,
                    publisher=publisher,
                )

        prescriptions = WriteNPlusOneAnalyzer().analyze(self._capture(create_in_a_loop))

        inserts = [p for p in prescriptions if p.extra.get("statement") == "insert"]
        assert len(inserts) == 1
        assert inserts[0].query_count == 4
        assert inserts[0].extra["table"] == "testapp_book"
        # The callsite must point into the loop, not into Django or this analyzer.
        assert inserts[0].callsite is not None
        assert inserts[0].callsite.filepath.endswith("test_write_nplusone.py")

    def test_save_in_a_loop_is_detected(self) -> None:
        """``obj.save()`` in a loop emits repeated UPDATEs."""
        for i in range(4):
            BookFactory(isbn=f"isbn-save-{i}")

        def save_in_a_loop() -> None:
            from tests.testapp.models import Book

            for book in Book.objects.all():
                book.title = f"{book.title}!"
                book.save()

        prescriptions = WriteNPlusOneAnalyzer().analyze(self._capture(save_in_a_loop))

        updates = [p for p in prescriptions if p.extra.get("statement") == "update"]
        assert len(updates) == 1
        assert updates[0].query_count == 4
        assert "bulk_update" in updates[0].fix_suggestion

    def test_bulk_create_produces_no_finding(self) -> None:
        """Positive control for the fix: applying the prescription clears the finding.

        Without this, an analyzer that flagged every INSERT would satisfy the
        detection tests above while prescribing a fix that does not work.
        """
        author = AuthorFactory()
        publisher = PublisherFactory()

        def use_bulk_create() -> None:
            from tests.testapp.models import Book

            Book.objects.bulk_create(
                [
                    Book(
                        title=f"t{i}",
                        isbn=f"isbn-bulk-{i}",
                        author=author,
                        publisher=publisher,
                    )
                    for i in range(4)
                ]
            )

        prescriptions = WriteNPlusOneAnalyzer().analyze(self._capture(use_bulk_create))

        assert [p for p in prescriptions if p.extra.get("statement") == "insert"] == []


class TestWriteNPlusOneNeverCrashes:
    """Key design decision 5: analysis failure must not propagate to the host app."""

    def test_internal_failure_returns_empty(self) -> None:
        """A crash inside detection is swallowed and reported as no findings."""
        from unittest.mock import patch

        analyzer = WriteNPlusOneAnalyzer()
        queries = _write('INSERT INTO "testapp_book" ("title") VALUES (%s)', 5)

        # Positive control: the same input produces a finding when nothing is broken,
        # so the empty result below is the except branch and not an input problem.
        assert len(analyzer.analyze(queries)) == 1

        with patch.object(analyzer, "_build_prescription", side_effect=RuntimeError("boom")):
            assert analyzer.analyze(queries) == []

    def test_unresolvable_table_still_reports(self) -> None:
        """A table no installed model owns is still a finding, with model=None.

        Raw cursor.execute() against a table Django does not manage is the real
        case. The fix suggestion falls back to the generic Model.objects wording.
        """
        queries = _write('INSERT INTO "legacy_audit_rows" ("payload") VALUES (%s)', 5)

        prescriptions = WriteNPlusOneAnalyzer().analyze(queries)

        assert len(prescriptions) == 1
        assert prescriptions[0].extra["model"] is None
        assert 'table "legacy_audit_rows"' in prescriptions[0].description
        assert "Model.objects.bulk_create" in prescriptions[0].fix_suggestion
