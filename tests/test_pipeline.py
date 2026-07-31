"""Tests for the consolidated analysis pipeline (FOLLOWUPS entry 4).

pipeline.analyze() is the single surface that every dispatch site routes
through: it runs discover_analyzers() over the UNFILTERED query list and then
filters the resulting prescriptions through .queryignore. The analyzer input is
never filtered -- that decision, and the harm avoided by it, is pinned by
TestAnalyzerInputNeverFiltered below (see the S4 plan section 2).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.test import override_settings

from query_doctor.conf import get_config
from query_doctor.pipeline import sort_by_apply_order
from query_doctor.reporters.console import ConsoleReporter
from query_doctor.types import (
    CallSite,
    CapturedQuery,
    DiagnosisReport,
    IssueType,
    Prescription,
    Severity,
)

_SQL = (
    'SELECT "blog_author"."id", "blog_author"."name" FROM "blog_author" '
    'WHERE "blog_author"."id" = %s'
)
_NORM = (
    'select "blog_author"."id", "blog_author"."name" from "blog_author" '
    'where "blog_author"."id" = ?'
)
_FP = "fp_author_by_id"


def _q(path: str, line: int, i: int) -> CapturedQuery:
    return CapturedQuery(
        sql=_SQL % i,
        params=(i,),
        duration_ms=2.0,
        fingerprint=_FP,
        normalized_sql=_NORM,
        callsite=CallSite(filepath=path, line_number=line, function_name="render"),
        is_select=True,
        tables=["blog_author"],
    )


def _aggregate_group() -> list[CapturedQuery]:
    """One N+1 of 12 queries: 9 from blog/views.py, 3 from legacy_app/."""
    return [_q("/app/blog/views.py", 42, i) for i in range(9)] + [
        _q("/app/legacy_app/serializers.py", 88, i) for i in range(9, 12)
    ]


def _write_ignore(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "custom.queryignore"
    path.write_text(body, encoding="utf-8")
    return path


class TestPipelineContract:
    """analyze() exists, takes a keyword-only source, and returns prescriptions."""

    def test_analyze_returns_prescriptions(self) -> None:
        from query_doctor.pipeline import analyze

        rx = analyze(_aggregate_group(), source="test")
        types = [p.issue_type.value for p in rx]
        assert "n_plus_one" in types


class TestAnalyzerInputNeverFiltered:
    """A file: rule matching a SUBSET of an aggregate group's queries must not
    change the finding attributed to a file the user did not ignore.

    Withholding those 3 legacy_app queries from the analyzer would re-run N+1
    on 9 queries and emit severity=warning/query_count=9 (S4 plan section 2).
    The prescription's own callsite is blog/views.py, which does not match the
    rule, so it must survive unchanged: critical / 12 / blog/views.py.
    """

    def test_subset_file_rule_leaves_aggregate_unchanged(self, tmp_path: Path) -> None:
        from query_doctor.pipeline import analyze

        ignore = _write_ignore(tmp_path, "file:*legacy_app/*\n")
        with override_settings(QUERY_DOCTOR={"QUERYIGNORE_PATH": str(ignore)}):
            get_config.cache_clear()
            try:
                rx = analyze(_aggregate_group(), source="test")
            finally:
                get_config.cache_clear()

        nplus = [p for p in rx if p.issue_type.value == "n_plus_one"]
        assert len(nplus) == 1
        p = nplus[0]
        assert p.severity == Severity.CRITICAL
        assert p.query_count == 12
        assert p.callsite is not None
        assert p.callsite.filepath == "/app/blog/views.py"


class TestPipelineIgnoreFiltering:
    """A rule matching the prescription's OWN callsite suppresses the finding."""

    def test_file_rule_on_own_callsite_suppresses(self, tmp_path: Path) -> None:
        from query_doctor.pipeline import analyze

        ignore = _write_ignore(tmp_path, "file:*blog/views.py*\n")
        with override_settings(QUERY_DOCTOR={"QUERYIGNORE_PATH": str(ignore)}):
            get_config.cache_clear()
            try:
                rx = analyze(_aggregate_group(), source="test")
            finally:
                get_config.cache_clear()

        assert [p for p in rx if p.issue_type.value == "n_plus_one"] == []

    def test_no_rules_keeps_finding(self, tmp_path: Path) -> None:
        """Positive control: with an empty .queryignore the finding survives."""
        from query_doctor.pipeline import analyze

        ignore = _write_ignore(tmp_path, "# nothing\n")
        with override_settings(QUERY_DOCTOR={"QUERYIGNORE_PATH": str(ignore)}):
            get_config.cache_clear()
            try:
                rx = analyze(_aggregate_group(), source="test")
            finally:
                get_config.cache_clear()

        assert any(p.issue_type.value == "n_plus_one" for p in rx)


@pytest.mark.django_db
class TestSurfacesHonorQueryignore:
    """The five newly-wired surfaces must suppress findings via .queryignore.

    Today only the middleware and fix_queries honour the file; these five load
    it after entry 4 consolidates them onto pipeline.analyze().
    """

    def test_context_manager_suppresses(self, tmp_path: Path) -> None:
        """A sql: rule matching the raw SQL of the N+1 queries suppresses it on
        a real surface -- proving both the new pipeline wiring and the raw-SQL
        route reach the context manager.
        """
        from query_doctor.context_managers import diagnose_queries
        from tests.factories import BookFactory
        from tests.testapp.models import Book

        for _ in range(5):
            BookFactory()

        ignore = _write_ignore(tmp_path, "sql:%testapp_author%\n")
        with override_settings(QUERY_DOCTOR={"QUERYIGNORE_PATH": str(ignore)}):
            get_config.cache_clear()
            try:
                with diagnose_queries() as report:
                    for book in Book.objects.all():
                        _ = book.author.name
            finally:
                get_config.cache_clear()

        types = [p.issue_type.value for p in report.prescriptions]
        assert "n_plus_one" not in types

    def test_context_manager_positive_control(self, tmp_path: Path) -> None:
        """Same run, a non-matching rule -> the N+1 finding survives."""
        from query_doctor.context_managers import diagnose_queries
        from tests.factories import BookFactory
        from tests.testapp.models import Book

        for _ in range(5):
            BookFactory()

        ignore = _write_ignore(tmp_path, "sql:%no_such_table%\n")
        with override_settings(QUERY_DOCTOR={"QUERYIGNORE_PATH": str(ignore)}):
            get_config.cache_clear()
            try:
                with diagnose_queries() as report:
                    for book in Book.objects.all():
                        _ = book.author.name
            finally:
                get_config.cache_clear()

        types = [p.issue_type.value for p in report.prescriptions]
        assert "n_plus_one" in types


class TestApplyOrder:
    """Entry 54: prescriptions interact, so the report states an order.

    Applying the prescribed `.select_related('author')` removes the N+1 and
    raises fat_select's column count for the base table. A user working the
    report top to bottom fixes the critical finding and watches the
    informational one grow, with nothing in the output saying that is
    expected.
    """

    @staticmethod
    def _rx(issue_type: IssueType) -> Prescription:
        """Build a minimal prescription of the given type."""
        return Prescription(
            issue_type=issue_type,
            severity=Severity.INFO,
            description=issue_type.value,
            fix_suggestion="",
            callsite=None,
        )

    def test_fat_select_sorts_after_nplusone(self) -> None:
        """The finding whose number the other one moves is read last."""
        ordered = sort_by_apply_order(
            [
                self._rx(IssueType.FAT_SELECT),
                self._rx(IssueType.N_PLUS_ONE),
            ]
        )
        assert [p.issue_type for p in ordered] == [
            IssueType.N_PLUS_ONE,
            IssueType.FAT_SELECT,
        ]

    def test_sort_is_stable_within_a_rank(self) -> None:
        """Two findings of the same type keep the order the analyzer produced."""
        first = self._rx(IssueType.N_PLUS_ONE)
        first.description = "first"
        second = self._rx(IssueType.N_PLUS_ONE)
        second.description = "second"
        ordered = sort_by_apply_order([first, second])
        assert [p.description for p in ordered] == ["first", "second"]

    def test_unknown_types_land_between_the_ends(self) -> None:
        """An unranked plugin issue type must not sort before the N+1 fixes."""
        ordered = sort_by_apply_order(
            [
                self._rx(IssueType.FAT_SELECT),
                self._rx(IssueType.MISSING_INDEX),
                self._rx(IssueType.N_PLUS_ONE),
            ]
        )
        assert ordered[0].issue_type == IssueType.N_PLUS_ONE
        assert ordered[-1].issue_type == IssueType.FAT_SELECT


class TestOrderingNote:
    """The console output must say that the two findings interact."""

    @staticmethod
    def _report(*types: IssueType) -> DiagnosisReport:
        """Build a report carrying one prescription per given type."""
        report = DiagnosisReport()
        report.prescriptions = [
            Prescription(
                issue_type=t,
                severity=Severity.INFO,
                description=t.value,
                fix_suggestion="",
                callsite=None,
            )
            for t in types
        ]
        return report

    @staticmethod
    def _flat(text: str) -> str:
        """Collapse whitespace: Rich hard-wraps the note to the panel width."""
        return " ".join(text.split())

    def test_note_is_present_when_both_findings_are(self) -> None:
        """N+1 plus fat SELECT is the interacting pair."""
        out = self._flat(
            ConsoleReporter().render(self._report(IssueType.N_PLUS_ONE, IssueType.FAT_SELECT))
        )
        assert "re-read the fat SELECT findings only after that" in out

    def test_note_is_absent_without_the_pair(self) -> None:
        """Negative control: a lone N+1 gets no ordering note."""
        out = self._flat(ConsoleReporter().render(self._report(IssueType.N_PLUS_ONE)))
        assert "re-read the fat SELECT findings" not in out
