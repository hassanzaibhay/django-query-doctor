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
