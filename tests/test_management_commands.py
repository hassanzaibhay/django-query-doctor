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

# Entry 60: these tests used to drive the command at a path absent from
# tests/testapp/urls.py. Every one of them therefore analysed zero queries and
# asserted against an empty report. They now use real fixture URLs.
NPLUSONE_URL = "/books/nplusone/"
CLEAN_URL = "/books/optimized/"
RAISES_URL = "/books/raises/"


class TestCheckQueriesCommand:
    """Tests for the check_queries management command."""

    @pytest.mark.django_db
    def test_runs_without_error(self) -> None:
        """Command should run successfully with default args."""
        call_command("check_queries", "--url", CLEAN_URL)

    @pytest.mark.django_db
    def test_console_format(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Command with --format console should produce text output."""
        BookFactory.create_batch(4)
        call_command("check_queries", "--format", "console", "--url", NPLUSONE_URL)
        captured = capsys.readouterr()
        assert "Query Doctor Report" in captured.out

    @pytest.mark.django_db
    def test_json_format(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Command with --format json should produce valid JSON output."""
        BookFactory.create_batch(4)
        call_command("check_queries", "--format", "json", "--url", NPLUSONE_URL)
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "summary" in data
        assert data["summary"]["total_queries"] > 0

    @pytest.mark.django_db
    def test_fail_on_critical_no_issues(self) -> None:
        """--fail-on critical should not fail when no critical issues."""
        call_command("check_queries", "--fail-on", "critical", "--url", CLEAN_URL)

    @pytest.mark.django_db
    def test_help_text(self) -> None:
        """Command should have a help string."""
        from query_doctor.management.commands.check_queries import Command

        assert Command.help


@pytest.mark.django_db
class TestCheckQueriesURLErrors:
    """Entry 60: an unusable --url must not read as a clean run.

    Analysing nothing and finding nothing are indistinguishable at the exit
    status, which is the worst failure mode available to a CI gate. These
    tests pin that the two unusable cases are reported, are distinguishable
    from each other, and are non-zero.
    """

    def test_unresolvable_url_fails_and_names_the_url(self) -> None:
        """A URL absent from ROOT_URLCONF is a usage error, not a clean report."""
        with pytest.raises(CommandError) as excinfo:
            call_command("check_queries", "--url", "/definitely/not/a/url/")
        message = str(excinfo.value)
        assert "/definitely/not/a/url/" in message
        assert "does not resolve" in message

    def test_view_exception_fails_and_is_not_conflated_with_resolution(self) -> None:
        """A view that raises is a different condition and says so."""
        BookFactory.create_batch(2)
        with pytest.raises(CommandError) as excinfo:
            call_command("check_queries", "--url", RAISES_URL)
        message = str(excinfo.value)
        assert RAISES_URL in message
        assert "RuntimeError" in message
        assert "view exploded on purpose" in message
        # The resolution failure has its own wording; the two must not merge.
        assert "does not resolve" not in message

    def test_resolvable_url_still_succeeds(self) -> None:
        """Positive control: a real URL is unaffected by the new checks."""
        BookFactory.create_batch(2)
        call_command("check_queries", "--url", NPLUSONE_URL)


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
        """--save-baseline writes a JSON file recording the issues it found."""
        import os

        BookFactory.create_batch(4)
        baseline_path = str(tmp_path / "baseline.json")
        call_command("check_queries", "--url", NPLUSONE_URL, f"--save-baseline={baseline_path}")
        assert os.path.exists(baseline_path)
        with open(baseline_path) as f:
            data = json.load(f)
        assert isinstance(data, dict)
        assert data["issues"], "positive control: the baseline must record real findings"

    def test_baseline_no_regression_exits_zero(self, tmp_path) -> None:
        """--fail-on-regression exits 0 when the run matches a non-empty baseline.

        Entry 61: the previous version of this test wrote an *empty* baseline
        and drove the command at a URL that produced nothing, so it compared
        0 against 0 and would have passed with --fail-on-regression deleted.
        It now records a baseline from a URL that really does produce findings
        and re-runs against the same URL, so the comparison is non-trivial.
        Its negative control is the sibling test below.
        """
        BookFactory.create_batch(4)
        baseline_path = str(tmp_path / "baseline.json")
        call_command("check_queries", "--url", NPLUSONE_URL, f"--save-baseline={baseline_path}")
        with open(baseline_path) as f:
            assert json.load(f)["issues"], "positive control: baseline is non-empty"

        call_command(
            "check_queries",
            "--url",
            NPLUSONE_URL,
            f"--baseline={baseline_path}",
            "--fail-on-regression",
        )

    def test_baseline_regression_exits_nonzero(self, tmp_path) -> None:
        """Negative control for the test above: a new issue must fail the run.

        Recorded against the optimized view, then re-run against the N+1 view.
        If --fail-on-regression were a no-op this test would fail, which is
        exactly what the pair is for.
        """
        BookFactory.create_batch(4)
        baseline_path = str(tmp_path / "baseline.json")
        call_command("check_queries", "--url", CLEAN_URL, f"--save-baseline={baseline_path}")

        with pytest.raises(CommandError) as excinfo:
            call_command(
                "check_queries",
                "--url",
                NPLUSONE_URL,
                f"--baseline={baseline_path}",
                "--fail-on-regression",
            )
        assert "regression" in str(excinfo.value)

    def test_baseline_version_mismatch_warns_without_failing(self, tmp_path) -> None:
        """A stale baseline version prints a non-blocking coverage-drift warning.

        Must not change the exit code (no CommandError) and must not use
        alarming "invalid" language -- it's a heads-up, not a validity error.
        """
        from io import StringIO

        # Record a real baseline for this URL, then age only its version
        # field. An empty baseline would make --fail-on-regression fire on
        # the run's own findings, which is a different test.
        BookFactory.create_batch(4)
        baseline_path = str(tmp_path / "baseline.json")
        call_command("check_queries", "--url", NPLUSONE_URL, f"--save-baseline={baseline_path}")
        with open(baseline_path) as f:
            baseline = json.load(f)
        baseline["version"] = "0.0.1"
        with open(baseline_path, "w") as f:
            json.dump(baseline, f)

        out = StringIO()
        call_command(
            "check_queries",
            "--url",
            NPLUSONE_URL,
            f"--baseline={baseline_path}",
            "--fail-on-regression",
            stdout=out,
        )
        output = out.getvalue()
        assert "analyzer coverage may differ between versions" in output
        assert "invalid" not in output.lower()

    def test_baseline_version_match_no_mismatch_warning(self, tmp_path) -> None:
        """A baseline matching the current version prints no drift warning."""
        from io import StringIO

        from query_doctor import __version__

        baseline_path = str(tmp_path / "baseline.json")
        with open(baseline_path, "w") as f:
            json.dump({"issues": {}, "version": __version__}, f)

        out = StringIO()
        call_command(
            "check_queries",
            "--url",
            NPLUSONE_URL,
            f"--baseline={baseline_path}",
            stdout=out,
        )
        output = out.getvalue()
        assert "analyzer coverage may differ between versions" not in output


@pytest.mark.django_db
class TestCheckQueriesGroupFlag:
    """Tests for check_queries --group flag."""

    def test_group_flag_does_not_crash(self) -> None:
        """--group flag runs without error."""
        call_command("check_queries", "--url", NPLUSONE_URL, "--group")


class TestURLPatterns:
    """Tests for query_doctor.urls."""

    def test_urlpatterns_importable_and_nonempty(self) -> None:
        """query_doctor.urls defines at least one URL pattern."""
        from query_doctor.urls import urlpatterns

        assert isinstance(urlpatterns, list)
        assert len(urlpatterns) > 0
