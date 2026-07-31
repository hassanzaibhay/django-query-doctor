"""Tests for diagnose_project management command."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.core.management import call_command

from tests.factories import AuthorFactory, BookFactory, PublisherFactory


@pytest.mark.django_db
class TestDiagnoseProjectCommand:
    """Tests for the diagnose_project management command."""

    def test_command_runs_successfully(self, tmp_path: Path) -> None:
        """Command runs without errors with default args."""
        output_path = tmp_path / "report.html"
        pub = PublisherFactory()
        author = AuthorFactory(publisher=pub)
        BookFactory(author=author, publisher=pub)

        call_command("diagnose_project", output=str(output_path))
        assert output_path.exists()

    def test_output_is_html(self, tmp_path: Path) -> None:
        """Default output is HTML format."""
        output_path = tmp_path / "report.html"
        call_command("diagnose_project", output=str(output_path))
        content = output_path.read_text()
        assert "<!DOCTYPE html>" in content

    def test_json_format(self, tmp_path: Path) -> None:
        """--format json produces JSON output."""
        output_path = tmp_path / "report.json"
        call_command("diagnose_project", output=str(output_path), format="json")
        assert output_path.exists()
        import json

        data = json.loads(output_path.read_text())
        assert "summary" in data

    def test_exclude_urls(self, tmp_path: Path) -> None:
        """--exclude-urls filters out matching patterns."""
        output_path = tmp_path / "report.html"
        call_command(
            "diagnose_project",
            output=str(output_path),
            exclude_urls=["/books/", "/admin/"],
        )
        assert output_path.exists()

    def test_apps_filter(self, tmp_path: Path) -> None:
        """--apps filters to specific app namespaces."""
        output_path = tmp_path / "report.html"
        call_command(
            "diagnose_project",
            output=str(output_path),
            apps=["nonexistent_app"],
        )
        assert output_path.exists()

    def test_handles_empty_project(self, tmp_path: Path) -> None:
        """Command handles a project with no matching URLs."""
        output_path = tmp_path / "report.html"
        call_command(
            "diagnose_project",
            output=str(output_path),
            exclude_urls=["/"],
        )
        assert output_path.exists()


@pytest.mark.django_db
class TestDiagnoseProjectBaseline:
    """Entry 58: the documented baseline workflow on this command had no test.

    `docs/guides/baseline.md` says "The `diagnose_project` command also
    supports baseline flags" and shows a worked invocation, but
    `tests/test_diagnose_project_command.py` contained no occurrence of
    `baseline` at all. The whole of `:243-261` -- load, find_regressions,
    find_resolved and every console branch -- was uncovered.
    """

    def _seed(self) -> None:
        """Create enough related data for the project scan to find issues."""
        pub = PublisherFactory()
        author = AuthorFactory(publisher=pub)
        BookFactory.create_batch(5, author=author, publisher=pub)

    def test_save_baseline_writes_a_snapshot(self, tmp_path: Path) -> None:
        """--save-baseline records the issues the scan found."""
        import json

        self._seed()
        baseline_path = tmp_path / "baseline.json"
        call_command(
            "diagnose_project",
            output=str(tmp_path / "report.html"),
            save_baseline=str(baseline_path),
        )
        assert baseline_path.exists()
        data = json.loads(baseline_path.read_text())
        assert data["issues"], "positive control: the scan must find something to record"

    def test_no_regression_against_its_own_baseline_exits_zero(self, tmp_path: Path) -> None:
        """Re-running against a baseline of the same project reports no change."""
        from io import StringIO

        self._seed()
        baseline_path = tmp_path / "baseline.json"
        call_command(
            "diagnose_project",
            output=str(tmp_path / "a.html"),
            save_baseline=str(baseline_path),
        )

        out = StringIO()
        call_command(
            "diagnose_project",
            output=str(tmp_path / "b.html"),
            baseline=str(baseline_path),
            fail_on_regression=True,
            stdout=out,
        )
        assert "No changes from baseline." in out.getvalue()

    def test_regression_against_an_empty_baseline_exits_nonzero(self, tmp_path: Path) -> None:
        """Negative control: new issues vs an empty baseline must fail the run.

        Without this the test above would pass against a --fail-on-regression
        that had been deleted.
        """
        import json

        from django.core.management.base import CommandError

        self._seed()
        baseline_path = tmp_path / "baseline.json"
        baseline_path.write_text(json.dumps({"issues": [], "version": "2.0.0"}))

        with pytest.raises(CommandError) as excinfo:
            call_command(
                "diagnose_project",
                output=str(tmp_path / "c.html"),
                baseline=str(baseline_path),
                fail_on_regression=True,
            )
        assert "regression" in str(excinfo.value)

    def test_resolved_issues_are_reported(self, tmp_path: Path) -> None:
        """A baseline holding an issue the scan no longer finds prints it as resolved."""
        import json
        from io import StringIO

        self._seed()
        baseline_path = tmp_path / "baseline.json"
        call_command(
            "diagnose_project",
            output=str(tmp_path / "d.html"),
            save_baseline=str(baseline_path),
        )
        data = json.loads(baseline_path.read_text())
        data["issues"].append(
            {
                "message": "a stale issue that no scan will ever produce again",
                "severity": "warning",
                "fingerprint": "never-going-to-be-found-again",
            }
        )
        baseline_path.write_text(json.dumps(data))

        out = StringIO()
        call_command(
            "diagnose_project",
            output=str(tmp_path / "e.html"),
            baseline=str(baseline_path),
            stdout=out,
        )
        assert "Resolved since baseline: 1 issue(s)" in out.getvalue()
