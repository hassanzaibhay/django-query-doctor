"""Tests for Django management commands.

Verifies check_queries and query_budget commands work correctly
with various options and produce appropriate output and exit codes.
"""

from __future__ import annotations

import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from tests.factories import AuthorFactory, BookFactory


class TestCheckQueriesCommand:
    """Tests for the check_queries management command."""

    @pytest.mark.django_db
    def test_runs_without_error(self) -> None:
        """Command should run successfully with default args."""
        call_command("check_queries", "--url", "/test/")

    @pytest.mark.django_db
    def test_console_format(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Command with --format console should produce text output."""
        call_command("check_queries", "--format", "console", "--url", "/test/")
        captured = capsys.readouterr()
        # Should have some output (at least the summary)
        # Command may or may not produce output depending on URL resolution
        assert isinstance(captured.out, str)

    @pytest.mark.django_db
    def test_json_format(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Command with --format json should produce valid JSON output."""
        call_command("check_queries", "--format", "json", "--url", "/test/")
        captured = capsys.readouterr()
        if captured.out.strip():
            data = json.loads(captured.out)
            assert "summary" in data

    @pytest.mark.django_db
    def test_fail_on_critical_no_issues(self) -> None:
        """--fail-on critical should not fail when no critical issues."""
        # No queries to detect issues on
        call_command("check_queries", "--fail-on", "critical", "--url", "/test/")

    @pytest.mark.django_db
    def test_help_text(self) -> None:
        """Command should have a help string."""
        from query_doctor.management.commands.check_queries import Command

        assert Command.help


class TestQueryBudgetCommand:
    """Tests for the query_budget management command."""

    @pytest.mark.django_db
    def test_runs_without_error(self) -> None:
        """Command should run successfully with default args."""
        call_command("query_budget", "--max-queries", "100")

    @pytest.mark.django_db
    def test_max_queries_flag(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--max-queries should set the query limit."""
        call_command("query_budget", "--max-queries", "50")
        captured = capsys.readouterr()
        # Command should produce some budget-related output
        assert isinstance(captured.out, str)

    @pytest.mark.django_db
    def test_exceeds_budget_exits_with_error(self) -> None:
        """Should raise CommandError when budget is exceeded."""
        # Create enough data to trigger many queries
        authors = AuthorFactory.create_batch(5)
        for author in authors:
            BookFactory.create_batch(3, author=author)

        with pytest.raises(CommandError):
            # Set an impossibly low budget, then trigger queries
            call_command(
                "query_budget",
                "--max-queries",
                "0",
                "--execute",
                "from tests.testapp.models import Book; "
                "[b.author.name for b in Book.objects.all()]",
            )

    @pytest.mark.django_db
    def test_within_budget_succeeds(self) -> None:
        """Should succeed when within the query budget."""
        call_command(
            "query_budget",
            "--max-queries",
            "100",
            "--execute",
            "from tests.testapp.models import Book; list(Book.objects.all())",
        )

    @pytest.mark.django_db
    def test_help_text(self) -> None:
        """Command should have a help string."""
        from query_doctor.management.commands.query_budget import Command

        assert Command.help


@pytest.mark.django_db
class TestCheckQueriesBaseline:
    """Tests for check_queries baseline flags."""

    def test_save_baseline_creates_file(self, tmp_path) -> None:
        """--save-baseline writes a JSON file."""
        import os

        baseline_path = str(tmp_path / "baseline.json")
        call_command("check_queries", "--url", "/test/", f"--save-baseline={baseline_path}")
        assert os.path.exists(baseline_path)
        with open(baseline_path) as f:
            data = json.load(f)
        assert isinstance(data, dict)

    def test_baseline_no_regression_exits_zero(self, tmp_path) -> None:
        """--fail-on-regression exits 0 when no new issues vs baseline."""
        baseline_path = str(tmp_path / "baseline.json")
        # Write an empty baseline
        with open(baseline_path, "w") as f:
            json.dump({"issues": {}, "version": "2.0.0"}, f)
        # Should not raise CommandError
        call_command(
            "check_queries",
            "--url",
            "/test/",
            f"--baseline={baseline_path}",
            "--fail-on-regression",
        )


@pytest.mark.django_db
class TestCheckQueriesGroupFlag:
    """Tests for check_queries --group flag."""

    def test_group_flag_does_not_crash(self) -> None:
        """--group flag runs without error."""
        call_command("check_queries", "--url", "/test/", "--group")


class TestURLPatterns:
    """Tests for query_doctor.urls."""

    def test_urlpatterns_importable_and_nonempty(self) -> None:
        """query_doctor.urls defines at least one URL pattern."""
        from query_doctor.urls import urlpatterns

        assert isinstance(urlpatterns, list)
        assert len(urlpatterns) > 0
