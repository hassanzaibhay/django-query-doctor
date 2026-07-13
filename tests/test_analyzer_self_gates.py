"""Tests for the is_enabled() self-gate on nplusone/duplicate/missing_index.

Prior to this gate, these three analyzers ignored ANALYZERS.<name>.enabled
entirely -- disabling one in QUERY_DOCTOR settings had no effect anywhere
except fix_queries. Each test below proves the gate via a real, currently-
ungated dispatch path (context_managers.diagnose_queries and the
check_queries management command), not via middleware: middleware's
_get_enabled_analyzers already filters by config upstream of analyze(), so a
disabled analyzer never reaches the method there and a green test through
that path would pass for the wrong reason (upstream filter, not this gate).

Every test feeds input that WOULD produce a finding if the analyzer were
enabled (so the `not queries` clause of the guard is never what causes an
empty result -- is_enabled() must be the only thing that can), and pairs the
disabled-returns-nothing assertion with an enabled-returns-something positive
control on the same fixture. Without the positive control, a test that feeds
no queries at all would pass "for free" and prove nothing about the gate.
"""

from __future__ import annotations

import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.test import override_settings

from query_doctor.conf import get_config
from query_doctor.context_managers import diagnose_queries
from query_doctor.types import IssueType
from tests.factories import BookFactory


def _run_check_queries(url: str) -> str:
    """Run check_queries --format json against url, return captured stdout."""
    out = StringIO()
    call_command("check_queries", "--format", "json", "--url", url, stdout=out)
    return out.getvalue()


@pytest.mark.django_db
class TestNPlusOneGate:
    """nplusone.py:120 analyze() must honor ANALYZERS.nplusone.enabled."""

    def test_context_manager_respects_disabled(self) -> None:
        for _ in range(5):
            BookFactory()

        with override_settings(QUERY_DOCTOR={"ANALYZERS": {"nplusone": {"enabled": False}}}):
            get_config.cache_clear()
            with diagnose_queries() as report:
                from tests.testapp.models import Book

                for book in Book.objects.all():
                    _ = book.author.name
            get_config.cache_clear()

        types = [p.issue_type for p in report.prescriptions]
        assert IssueType.N_PLUS_ONE not in types

    def test_context_manager_positive_control_enabled(self) -> None:
        for _ in range(5):
            BookFactory()

        with override_settings(QUERY_DOCTOR={"ANALYZERS": {"nplusone": {"enabled": True}}}):
            get_config.cache_clear()
            with diagnose_queries() as report:
                from tests.testapp.models import Book

                for book in Book.objects.all():
                    _ = book.author.name
            get_config.cache_clear()

        types = [p.issue_type for p in report.prescriptions]
        assert IssueType.N_PLUS_ONE in types

    def test_check_queries_respects_disabled(self) -> None:
        for _ in range(5):
            BookFactory()

        with override_settings(QUERY_DOCTOR={"ANALYZERS": {"nplusone": {"enabled": False}}}):
            get_config.cache_clear()
            out = _run_check_queries("/books/nplusone/")
            get_config.cache_clear()

        data = json.loads(out)
        types = [p["issue_type"] for p in data["prescriptions"]]
        assert IssueType.N_PLUS_ONE.value not in types

    def test_check_queries_positive_control_enabled(self) -> None:
        for _ in range(5):
            BookFactory()

        with override_settings(QUERY_DOCTOR={"ANALYZERS": {"nplusone": {"enabled": True}}}):
            get_config.cache_clear()
            out = _run_check_queries("/books/nplusone/")
            get_config.cache_clear()

        data = json.loads(out)
        types = [p["issue_type"] for p in data["prescriptions"]]
        assert IssueType.N_PLUS_ONE.value in types


@pytest.mark.django_db
class TestDuplicateGate:
    """duplicate.py:44 analyze() must honor ANALYZERS.duplicate.enabled."""

    def test_context_manager_respects_disabled(self) -> None:
        BookFactory()

        with override_settings(QUERY_DOCTOR={"ANALYZERS": {"duplicate": {"enabled": False}}}):
            get_config.cache_clear()
            with diagnose_queries() as report:
                from tests.testapp.models import Book

                list(Book.objects.filter(price=19.99))
                list(Book.objects.filter(price=19.99))
                list(Book.objects.filter(price=19.99))
            get_config.cache_clear()

        types = [p.issue_type for p in report.prescriptions]
        assert IssueType.DUPLICATE_QUERY not in types

    def test_context_manager_positive_control_enabled(self) -> None:
        BookFactory()

        with override_settings(QUERY_DOCTOR={"ANALYZERS": {"duplicate": {"enabled": True}}}):
            get_config.cache_clear()
            with diagnose_queries() as report:
                from tests.testapp.models import Book

                list(Book.objects.filter(price=19.99))
                list(Book.objects.filter(price=19.99))
                list(Book.objects.filter(price=19.99))
            get_config.cache_clear()

        types = [p.issue_type for p in report.prescriptions]
        assert IssueType.DUPLICATE_QUERY in types

    def test_check_queries_respects_disabled(self) -> None:
        BookFactory()

        with override_settings(QUERY_DOCTOR={"ANALYZERS": {"duplicate": {"enabled": False}}}):
            get_config.cache_clear()
            out = _run_check_queries("/books/duplicate/")
            get_config.cache_clear()

        data = json.loads(out)
        types = [p["issue_type"] for p in data["prescriptions"]]
        assert IssueType.DUPLICATE_QUERY.value not in types

    def test_check_queries_positive_control_enabled(self) -> None:
        BookFactory()

        with override_settings(QUERY_DOCTOR={"ANALYZERS": {"duplicate": {"enabled": True}}}):
            get_config.cache_clear()
            out = _run_check_queries("/books/duplicate/")
            get_config.cache_clear()

        data = json.loads(out)
        types = [p["issue_type"] for p in data["prescriptions"]]
        assert IssueType.DUPLICATE_QUERY.value in types


@pytest.mark.django_db
class TestMissingIndexGate:
    """missing_index.py:148 analyze() must honor ANALYZERS.missing_index.enabled."""

    def test_context_manager_respects_disabled(self) -> None:
        BookFactory()

        with override_settings(QUERY_DOCTOR={"ANALYZERS": {"missing_index": {"enabled": False}}}):
            get_config.cache_clear()
            with diagnose_queries() as report:
                from tests.testapp.models import Book

                list(Book.objects.filter(published_date="2024-01-01"))
            get_config.cache_clear()

        types = [p.issue_type for p in report.prescriptions]
        assert IssueType.MISSING_INDEX not in types

    def test_context_manager_positive_control_enabled(self) -> None:
        BookFactory()

        with override_settings(QUERY_DOCTOR={"ANALYZERS": {"missing_index": {"enabled": True}}}):
            get_config.cache_clear()
            with diagnose_queries() as report:
                from tests.testapp.models import Book

                list(Book.objects.filter(published_date="2024-01-01"))
            get_config.cache_clear()

        types = [p.issue_type for p in report.prescriptions]
        assert IssueType.MISSING_INDEX in types

    def test_check_queries_respects_disabled(self) -> None:
        BookFactory()

        with override_settings(QUERY_DOCTOR={"ANALYZERS": {"missing_index": {"enabled": False}}}):
            get_config.cache_clear()
            out = _run_check_queries("/books/missing-index/")
            get_config.cache_clear()

        data = json.loads(out)
        types = [p["issue_type"] for p in data["prescriptions"]]
        assert IssueType.MISSING_INDEX.value not in types

    def test_check_queries_positive_control_enabled(self) -> None:
        BookFactory()

        with override_settings(QUERY_DOCTOR={"ANALYZERS": {"missing_index": {"enabled": True}}}):
            get_config.cache_clear()
            out = _run_check_queries("/books/missing-index/")
            get_config.cache_clear()

        data = json.loads(out)
        types = [p["issue_type"] for p in data["prescriptions"]]
        assert IssueType.MISSING_INDEX.value in types
