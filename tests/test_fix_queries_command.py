"""Tests for the fix_queries management command."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.management import CommandError, call_command


class TestFixQueriesCommand:
    """Tests for the fix_queries management command."""

    def test_dry_run_produces_diff_no_file_modification(self, tmp_path: Path) -> None:
        """--dry-run should show diff but not modify files."""
        source = tmp_path / "views.py"
        original = (
            "from myapp.models import Book\n"
            "\n"
            "def get_books():\n"
            "    books = Book.objects.all()\n"
            "    return books\n"
        )
        source.write_text(original)
        out = StringIO()

        from query_doctor.fixer import ProposedFix
        from query_doctor.types import CallSite, IssueType, Prescription, Severity

        mock_fixes = [
            ProposedFix(
                file_path=str(source),
                original_line="    books = Book.objects.all()\n",
                fixed_line="    books = Book.objects.all().select_related('author')\n",
                line_number=4,
                description="Add select_related",
                prescription=Prescription(
                    issue_type=IssueType.N_PLUS_ONE,
                    severity=Severity.WARNING,
                    description="N+1",
                    fix_suggestion="select_related",
                    callsite=CallSite(str(source), 4, "get_books"),
                ),
            )
        ]

        with patch(
            "query_doctor.management.commands.fix_queries.Command._get_fixes",
            return_value=mock_fixes,
        ):
            call_command("fix_queries", "--dry-run", stdout=out)

        # File should NOT be modified
        assert source.read_text() == original
        output = out.getvalue()
        assert "select_related" in output

    def test_apply_modifies_files_with_backup(self, tmp_path: Path) -> None:
        """--apply should modify files and create .bak backups for an auto-appliable type."""
        source = tmp_path / "views.py"
        original = "def count_books(qs):\n    total = len(qs)\n    return total\n"
        source.write_text(original)
        out = StringIO()

        from query_doctor.fixer import ProposedFix
        from query_doctor.types import CallSite, IssueType, Prescription, Severity

        mock_fixes = [
            ProposedFix(
                file_path=str(source),
                original_line="    total = len(qs)\n",
                fixed_line="    total = qs.count()\n",
                line_number=2,
                description="Replace len() with count()",
                prescription=Prescription(
                    issue_type=IssueType.QUERYSET_EVAL,
                    severity=Severity.WARNING,
                    description="QuerySet eval",
                    fix_suggestion="count()",
                    callsite=CallSite(str(source), 1, "get_books"),
                ),
            )
        ]

        with patch(
            "query_doctor.management.commands.fix_queries.Command._get_fixes",
            return_value=mock_fixes,
        ):
            call_command("fix_queries", "--apply", stdout=out)

        assert "qs.count()" in source.read_text()
        backup = Path(str(source) + ".bak")
        assert backup.exists()

    def test_apply_raises_command_error_on_skipped_unsafe(self, tmp_path: Path) -> None:
        """--apply exits nonzero when unsafe fixes are skipped, but still prints the diff."""
        source = tmp_path / "views.py"
        source.write_text("    books = Book.objects.all()\n")
        out = StringIO()

        from query_doctor.fixer import ProposedFix
        from query_doctor.types import CallSite, IssueType, Prescription, Severity

        mock_fixes = [
            ProposedFix(
                file_path=str(source),
                original_line="    books = Book.objects.all()\n",
                fixed_line="    books = Book.objects.all().select_related('author')\n",
                line_number=1,
                description="Add select_related",
                prescription=Prescription(
                    issue_type=IssueType.N_PLUS_ONE,
                    severity=Severity.WARNING,
                    description="N+1",
                    fix_suggestion="select_related",
                    callsite=CallSite(str(source), 1, "get_books"),
                ),
            )
        ]

        with (
            patch(
                "query_doctor.management.commands.fix_queries.Command._get_fixes",
                return_value=mock_fixes,
            ),
            pytest.raises(CommandError),
        ):
            call_command("fix_queries", "--apply", stdout=out)

        output = out.getvalue()
        assert "select_related" in output
        assert source.read_text() == "    books = Book.objects.all()\n"

    def test_apply_raises_command_error_on_failed_validation(self, tmp_path: Path) -> None:
        """--apply exits nonzero when an auto-appliable fix fails the ast.parse floor."""
        source = tmp_path / "views.py"
        source.write_text("x = 1\n")
        out = StringIO()

        from query_doctor.fixer import ProposedFix
        from query_doctor.types import CallSite, IssueType, Prescription, Severity

        mock_fixes = [
            ProposedFix(
                file_path=str(source),
                original_line="x = 1\n",
                fixed_line="x = (\n",
                line_number=1,
                description="Broken fix",
                prescription=Prescription(
                    issue_type=IssueType.QUERYSET_EVAL,
                    severity=Severity.WARNING,
                    description="QuerySet eval",
                    fix_suggestion="count()",
                    callsite=CallSite(str(source), 1, "get_books"),
                ),
            )
        ]

        with (
            patch(
                "query_doctor.management.commands.fix_queries.Command._get_fixes",
                return_value=mock_fixes,
            ),
            pytest.raises(CommandError),
        ):
            call_command("fix_queries", "--apply", stdout=out)

        assert source.read_text() == "x = 1\n"
        assert not (tmp_path / "views.py.bak").exists()

    def test_issue_type_filter(self) -> None:
        """--issue-type should filter fixes by issue type."""
        out = StringIO()

        from query_doctor.fixer import ProposedFix
        from query_doctor.types import CallSite, IssueType, Prescription, Severity

        mock_fixes = [
            ProposedFix(
                file_path="/tmp/views.py",
                original_line="line1\n",
                fixed_line="line1_fixed\n",
                line_number=1,
                description="N+1 fix",
                prescription=Prescription(
                    issue_type=IssueType.N_PLUS_ONE,
                    severity=Severity.WARNING,
                    description="N+1",
                    fix_suggestion="fix",
                    callsite=CallSite("/tmp/views.py", 1, "get"),
                ),
            ),
            ProposedFix(
                file_path="/tmp/views.py",
                original_line="line2\n",
                fixed_line="line2_fixed\n",
                line_number=2,
                description="Duplicate fix",
                prescription=Prescription(
                    issue_type=IssueType.DUPLICATE_QUERY,
                    severity=Severity.WARNING,
                    description="Dup",
                    fix_suggestion="fix",
                    callsite=CallSite("/tmp/views.py", 2, "get"),
                ),
            ),
        ]

        with patch(
            "query_doctor.management.commands.fix_queries.Command._get_fixes",
            return_value=mock_fixes,
        ):
            call_command("fix_queries", "--dry-run", "--issue-type", "n_plus_one", stdout=out)

        output = out.getvalue()
        assert "N+1 fix" in output
        # Duplicate fix should be filtered out
        assert "Duplicate fix" not in output

    def test_file_filter(self) -> None:
        """--file should filter fixes to specific files."""
        out = StringIO()

        from query_doctor.fixer import ProposedFix
        from query_doctor.types import CallSite, IssueType, Prescription, Severity

        mock_fixes = [
            ProposedFix(
                file_path="myapp/views.py",
                original_line="line1\n",
                fixed_line="line1_fixed\n",
                line_number=1,
                description="Views fix",
                prescription=Prescription(
                    issue_type=IssueType.N_PLUS_ONE,
                    severity=Severity.WARNING,
                    description="N+1",
                    fix_suggestion="fix",
                    callsite=CallSite("myapp/views.py", 1, "get"),
                ),
            ),
            ProposedFix(
                file_path="myapp/serializers.py",
                original_line="line2\n",
                fixed_line="line2_fixed\n",
                line_number=2,
                description="Serializer fix",
                prescription=Prescription(
                    issue_type=IssueType.N_PLUS_ONE,
                    severity=Severity.WARNING,
                    description="N+1",
                    fix_suggestion="fix",
                    callsite=CallSite("myapp/serializers.py", 2, "get"),
                ),
            ),
        ]

        with patch(
            "query_doctor.management.commands.fix_queries.Command._get_fixes",
            return_value=mock_fixes,
        ):
            call_command("fix_queries", "--dry-run", "--file", "myapp/views.py", stdout=out)

        output = out.getvalue()
        assert "Views fix" in output
        assert "Serializer fix" not in output
