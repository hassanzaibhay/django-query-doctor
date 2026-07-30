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

    def test_multi_row_inserts_are_never_flagged(self) -> None:
        """A multi-row INSERT is the prescribed fix and must never be the finding.

        Five of them, so this fails if the rule only passes because a single
        capture sits below the threshold -- which is what an earlier version of
        this test actually asserted, despite its name.
        """
        bulk = _write(
            'INSERT INTO "testapp_book" ("title") VALUES (%s), (%s), (%s), (%s), (%s)',
            5,
        )

        assert WriteNPlusOneAnalyzer().analyze(bulk) == []

    def test_single_row_insert_is_still_flagged_at_the_same_count(self) -> None:
        """Positive control for the multi-row rule.

        Identical shape and count as the test above, one tuple instead of five.
        Without this, a rule that rejected every INSERT would pass that test.
        """
        single = _write('INSERT INTO "testapp_book" ("title") VALUES (%s)', 5)

        assert len(WriteNPlusOneAnalyzer().analyze(single)) == 1

    def test_a_parenthesised_value_is_not_counted_as_a_row(self) -> None:
        """Row counting is depth-aware, so a subquery inside one row stays one row."""
        nested = _write(
            'INSERT INTO "testapp_book" ("title", "author_id") '
            'VALUES (%s, (SELECT "id" FROM "testapp_author" WHERE "name" = %s))',
            5,
        )

        prescriptions = WriteNPlusOneAnalyzer().analyze(nested)

        assert len(prescriptions) == 1
        assert prescriptions[0].extra["statement"] == "insert"

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

    def test_a_multi_value_in_list_is_bulk(self) -> None:
        """An UPDATE or DELETE targeting several ids at once is already the bulk form."""
        for statement in (
            'UPDATE "testapp_book" SET "title" = %s WHERE "id" IN (%s, %s, %s)',
            'DELETE FROM "testapp_book" WHERE "id" IN (%s, %s, %s)',
        ):
            assert WriteNPlusOneAnalyzer().analyze(_write(statement, 5)) == [], statement

    def test_a_single_value_in_list_is_single_row(self) -> None:
        """Positive control for the rule above: one value in the list is one row.

        Django emits exactly this for ``obj.delete()``. Without this test, a rule
        that rejected every IN list would satisfy the test above while silencing
        the per-object delete loop the analyzer exists to find.
        """
        for statement in (
            'UPDATE "testapp_book" SET "title" = %s WHERE "id" IN (%s)',
            'DELETE FROM "testapp_book" WHERE "id" IN (%s)',
        ):
            assert len(WriteNPlusOneAnalyzer().analyze(_write(statement, 5))) == 1, statement

    def test_any_in_list_over_one_value_rejects(self) -> None:
        """With several IN lists, more than one value in any of them is enough."""
        statement = (
            'DELETE FROM "testapp_book" WHERE "author_id" IN (%s) AND "publisher_id" IN (%s, %s)'
        )

        assert WriteNPlusOneAnalyzer().analyze(_write(statement, 5)) == []

    def test_a_nested_tuple_inside_a_value_is_not_counted(self) -> None:
        """Item counting is depth-aware, so a nested call does not inflate the count."""
        statement = 'DELETE FROM "testapp_book" WHERE "id" IN (COALESCE(%s, %s))'

        assert len(WriteNPlusOneAnalyzer().analyze(_write(statement, 5))) == 1

    def test_in_subquery_is_treated_as_single_row(self) -> None:
        """Documented limitation: a subquery's cardinality is not in the statement.

        ``WHERE id IN (SELECT ...)`` holds no value list, so it reads as single-row
        and a loop issuing it is reported. Pinned so the behaviour is deliberate
        rather than incidental -- see the limitations section of the analyzer guide.
        """
        statement = (
            'DELETE FROM "testapp_book" '
            'WHERE "id" IN (SELECT "book_id" FROM "testapp_review" WHERE "rating" < %s)'
        )

        prescriptions = WriteNPlusOneAnalyzer().analyze(_write(statement, 5))

        assert len(prescriptions) == 1
        assert prescriptions[0].extra["statement"] == "delete"

    def test_a_bare_where_clause_is_treated_as_single_row(self) -> None:
        """Documented limitation: ``filter(status="x").delete()`` has no IN list.

        It emits ``WHERE "status" = %s`` and may affect any number of rows, which
        statement shape cannot reveal. Reported as single-row, by design.
        """
        statement = 'DELETE FROM "testapp_book" WHERE "title" = %s'

        assert len(WriteNPlusOneAnalyzer().analyze(_write(statement, 5))) == 1

    def test_statements_with_no_row_tuples_are_single_row(self) -> None:
        """``INSERT ... SELECT`` and ``DEFAULT VALUES`` carry no tuples.

        Neither is a bulk insert, so a loop issuing either is still a finding.
        ``DEFAULT VALUES`` is the one that could go wrong quietly: it contains the
        VALUES keyword, so the count has to come from the tuples rather than from
        the keyword's presence.
        """
        for statement in (
            'INSERT INTO "testapp_book" ("title") SELECT "title" FROM "old_book"',
            'INSERT INTO "testapp_book" DEFAULT VALUES',
        ):
            prescriptions = WriteNPlusOneAnalyzer().analyze(_write(statement, 5))

            assert len(prescriptions) == 1, statement
            assert prescriptions[0].extra["statement"] == "insert"

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

    def _books(self, count: int, tag: str) -> list:
        """Create ``count`` books outside any capture window."""
        from tests.testapp.models import Book

        author = AuthorFactory()
        publisher = PublisherFactory()
        return [
            Book.objects.create(
                title=f"{tag}{i}",
                isbn=f"{tag}-{i}",
                author=author,
                publisher=publisher,
            )
            for i in range(count)
        ]

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

    def test_batched_bulk_create_produces_no_finding(self) -> None:
        """Regression: bulk_create(batch_size=N) splits into several INSERTs.

        Nine objects at batch_size=3 emit three multi-row INSERTs sharing one
        fingerprint, which clears the default threshold of 3. Before the
        multi-row check this reported "3 single-row INSERT statements" -- the
        prescribed fix reported as the defect, and reachable without user error
        because Django also batches when the backend caps parameters per
        statement (SQLite's 999-variable limit, MySQL's packet size).
        """
        author = AuthorFactory()
        publisher = PublisherFactory()

        def batched_bulk_create() -> None:
            from tests.testapp.models import Book

            Book.objects.bulk_create(
                [
                    Book(
                        title=f"t{i}",
                        isbn=f"isbn-batch-{i}",
                        author=author,
                        publisher=publisher,
                    )
                    for i in range(9)
                ],
                batch_size=3,
            )

        captured = self._capture(batched_bulk_create)

        # The premise of the regression: three same-fingerprint INSERTs really
        # were captured, so an empty result below cannot come from capturing none.
        inserts = [q for q in captured if q.normalized_sql.lstrip().startswith("insert")]
        assert len(inserts) == 3
        assert len({q.fingerprint for q in inserts}) == 1

        assert WriteNPlusOneAnalyzer().analyze(captured) == []

    def test_batched_bulk_update_produces_no_finding(self) -> None:
        """Regression: bulk_update(batch_size=N) splits into several UPDATEs.

        Same mechanism as the batched bulk_create case, for the second of the
        three bulk forms this analyzer prescribes. Nine objects at batch_size=3
        emit three multi-row UPDATEs sharing one fingerprint, clearing the
        default threshold -- so the analyzer reported the very call that produced
        them.
        """
        from tests.testapp.models import Book

        books = self._books(9, "bu")
        for i, book in enumerate(books):
            book.title = f"new{i}"

        def batched_bulk_update() -> None:
            Book.objects.bulk_update(books, ["title"], batch_size=3)

        captured = self._capture(batched_bulk_update)

        updates = [q for q in captured if q.normalized_sql.lstrip().startswith("update")]
        assert len(updates) == 3
        assert len({q.fingerprint for q in updates}) == 1

        assert WriteNPlusOneAnalyzer().analyze(captured) == []

    def test_batched_queryset_delete_produces_no_finding(self) -> None:
        """Regression: repeated queryset deletes each target many rows.

        Three ``filter(pk__in=chunk).delete()`` calls over nine books. Every
        cascade table gets its own fingerprint group, so the assertion covers all
        of them rather than only Book -- an earlier version of this rule that
        only looked at the primary table would have left the cascade findings.
        """
        from tests.testapp.models import Book

        ids = [b.pk for b in self._books(9, "dl")]

        def batched_queryset_delete() -> None:
            for chunk in (ids[0:3], ids[3:6], ids[6:9]):
                Book.objects.filter(pk__in=chunk).delete()

        captured = self._capture(batched_queryset_delete)

        deletes = [q for q in captured if q.normalized_sql.lstrip().startswith("delete")]
        assert len(deletes) == 9
        assert len({q.fingerprint for q in deletes}) == 3

        assert WriteNPlusOneAnalyzer().analyze(captured) == []

    def test_save_in_a_loop_still_fires(self) -> None:
        """Positive control: the rule must not silence the canonical save loop.

        A per-object save emits ``SET ... WHERE "id" = %s`` with no IN list at
        all, so the IN-cardinality rule leaves it alone. A rule that killed this
        would be worse than the false positive it was written to fix.
        """
        from tests.testapp.models import Book

        self._books(4, "sv")

        def save_in_a_loop() -> None:
            for book in Book.objects.all():
                book.title = f"{book.title}!"
                book.save()

        prescriptions = WriteNPlusOneAnalyzer().analyze(self._capture(save_in_a_loop))

        updates = [p for p in prescriptions if p.extra.get("statement") == "update"]
        assert len(updates) == 1
        assert updates[0].query_count == 4

    def test_delete_in_a_loop_still_fires(self) -> None:
        """Positive control: per-object delete emits IN with one placeholder.

        This is the control a normalized-form rule cannot pass. Normalization
        collapses ``IN (...)`` to ``IN (?)``, so a single-object delete and a
        batched queryset delete are normalized-identical -- only the raw
        statement distinguishes them.
        """
        books = self._books(4, "dloop")

        def delete_in_a_loop() -> None:
            for book in books:
                book.delete()

        prescriptions = WriteNPlusOneAnalyzer().analyze(self._capture(delete_in_a_loop))

        book_deletes = [
            p
            for p in prescriptions
            if p.extra.get("statement") == "delete" and p.extra.get("table") == "testapp_book"
        ]
        assert len(book_deletes) == 1
        assert book_deletes[0].query_count == 4

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
