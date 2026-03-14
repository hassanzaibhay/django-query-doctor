"""Tests for the QueryFixer engine."""

from __future__ import annotations

from pathlib import Path

from query_doctor.fixer import ProposedFix, QueryFixer
from query_doctor.types import CallSite, IssueType, Prescription, Severity


def _make_prescription(
    issue_type: IssueType = IssueType.N_PLUS_ONE,
    filepath: str = "myapp/views.py",
    line_number: int = 5,
    fix_suggestion: str = "Add .select_related('author') to the queryset",
) -> Prescription:
    """Create a Prescription for testing."""
    return Prescription(
        issue_type=issue_type,
        severity=Severity.WARNING,
        description="Test issue",
        fix_suggestion=fix_suggestion,
        callsite=CallSite(
            filepath=filepath,
            line_number=line_number,
            function_name="get_queryset",
        ),
    )


class TestQueryFixerGenerateFixes:
    """Tests for fix generation."""

    def test_nplusone_adds_select_related(self, tmp_path: Path) -> None:
        """N+1 fix should add select_related to queryset line."""
        source = tmp_path / "views.py"
        source.write_text(
            "from myapp.models import Book\n"
            "\n"
            "def get_books():\n"
            "    books = Book.objects.all()\n"
            "    return books\n"
        )
        rx = _make_prescription(
            issue_type=IssueType.N_PLUS_ONE,
            filepath=str(source),
            line_number=4,
            fix_suggestion="Add .select_related('author') to the queryset",
        )
        fixer = QueryFixer()
        fixes = fixer.generate_fixes([rx])
        assert len(fixes) == 1
        assert ".select_related('author')" in fixes[0].fixed_line

    def test_duplicate_adds_todo_comment(self, tmp_path: Path) -> None:
        """Duplicate fix should add TODO comment."""
        source = tmp_path / "views.py"
        source.write_text(
            "from myapp.models import Book\n"
            "\n"
            "def get_books():\n"
            "    books = Book.objects.all()\n"
            "    return books\n"
        )
        rx = _make_prescription(
            issue_type=IssueType.DUPLICATE_QUERY,
            filepath=str(source),
            line_number=4,
            fix_suggestion="Cache this query result",
        )
        fixer = QueryFixer()
        fixes = fixer.generate_fixes([rx])
        assert len(fixes) == 1
        assert "TODO" in fixes[0].fixed_line

    def test_fat_select_adds_only(self, tmp_path: Path) -> None:
        """Fat SELECT fix should add .only() clause."""
        source = tmp_path / "views.py"
        source.write_text(
            "from myapp.models import Book\n"
            "\n"
            "def get_books():\n"
            "    books = Book.objects.all()\n"
            "    return books\n"
        )
        rx = _make_prescription(
            issue_type=IssueType.FAT_SELECT,
            filepath=str(source),
            line_number=4,
            fix_suggestion="Add .only('id', 'title') or .defer('content') to the queryset",
        )
        fixer = QueryFixer()
        fixes = fixer.generate_fixes([rx])
        assert len(fixes) == 1
        assert ".only(" in fixes[0].fixed_line or ".defer(" in fixes[0].fixed_line

    def test_queryset_eval_replaces_len(self, tmp_path: Path) -> None:
        """QuerySet eval fix should replace len(qs) with qs.count()."""
        source = tmp_path / "views.py"
        source.write_text(
            "from myapp.models import Book\n"
            "\n"
            "def count_books():\n"
            "    qs = Book.objects.all()\n"
            "    total = len(qs)\n"
            "    return total\n"
        )
        rx = _make_prescription(
            issue_type=IssueType.QUERYSET_EVAL,
            filepath=str(source),
            line_number=5,
            fix_suggestion="Replace len(queryset) with queryset.count()",
        )
        fixer = QueryFixer()
        fixes = fixer.generate_fixes([rx])
        assert len(fixes) == 1
        assert ".count()" in fixes[0].fixed_line

    def test_missing_callsite_skipped(self) -> None:
        """Prescription with no callsite should be skipped."""
        rx = Prescription(
            issue_type=IssueType.N_PLUS_ONE,
            severity=Severity.WARNING,
            description="Test",
            fix_suggestion="Fix it",
            callsite=None,
        )
        fixer = QueryFixer()
        fixes = fixer.generate_fixes([rx])
        assert len(fixes) == 0

    def test_missing_fix_suggestion_skipped(self, tmp_path: Path) -> None:
        """Prescription with no fix_suggestion should be skipped."""
        rx = Prescription(
            issue_type=IssueType.N_PLUS_ONE,
            severity=Severity.WARNING,
            description="Test",
            fix_suggestion="",
            callsite=CallSite("myapp/views.py", 10, "get"),
        )
        fixer = QueryFixer()
        fixes = fixer.generate_fixes([rx])
        assert len(fixes) == 0

    def test_nonexistent_file_skipped(self) -> None:
        """Fix on non-existent file should be skipped gracefully."""
        rx = _make_prescription(filepath="/nonexistent/path/views.py")
        fixer = QueryFixer()
        fixes = fixer.generate_fixes([rx])
        assert len(fixes) == 0


class TestQueryFixerGenerateDiff:
    """Tests for diff generation."""

    def test_generates_diff_output(self, tmp_path: Path) -> None:
        """generate_diff should produce unified diff format."""
        fix = ProposedFix(
            file_path=str(tmp_path / "views.py"),
            original_line="    books = Book.objects.all()\n",
            fixed_line="    books = Book.objects.all().select_related('author')\n",
            line_number=4,
            description="Add select_related",
            prescription=_make_prescription(),
        )
        fixer = QueryFixer()
        diff = fixer.generate_diff([fix])
        assert "---" in diff or "-" in diff
        assert "select_related" in diff


class TestQueryFixerApplyFixes:
    """Tests for applying fixes to disk."""

    def test_apply_modifies_files(self, tmp_path: Path) -> None:
        """--apply should modify files on disk."""
        source = tmp_path / "views.py"
        source.write_text(
            "from myapp.models import Book\n"
            "\n"
            "def get_books():\n"
            "    books = Book.objects.all()\n"
            "    return books\n"
        )
        fix = ProposedFix(
            file_path=str(source),
            original_line="    books = Book.objects.all()\n",
            fixed_line="    books = Book.objects.all().select_related('author')\n",
            line_number=4,
            description="Add select_related",
            prescription=_make_prescription(filepath=str(source)),
        )
        fixer = QueryFixer()
        modified = fixer.apply_fixes([fix])
        assert str(source) in modified
        content = source.read_text()
        assert ".select_related('author')" in content

    def test_apply_creates_backup(self, tmp_path: Path) -> None:
        """--apply should create .bak backup files."""
        source = tmp_path / "views.py"
        source.write_text("original content\n")
        fix = ProposedFix(
            file_path=str(source),
            original_line="original content\n",
            fixed_line="fixed content\n",
            line_number=1,
            description="Test fix",
            prescription=_make_prescription(filepath=str(source)),
        )
        fixer = QueryFixer()
        fixer.apply_fixes([fix], backup=True)
        backup = tmp_path / "views.py.bak"
        assert backup.exists()
        assert backup.read_text() == "original content\n"

    def test_apply_no_backup_when_disabled(self, tmp_path: Path) -> None:
        """No .bak should be created when backup=False."""
        source = tmp_path / "views.py"
        source.write_text("original content\n")
        fix = ProposedFix(
            file_path=str(source),
            original_line="original content\n",
            fixed_line="fixed content\n",
            line_number=1,
            description="Test fix",
            prescription=_make_prescription(filepath=str(source)),
        )
        fixer = QueryFixer()
        fixer.apply_fixes([fix], backup=False)
        backup = tmp_path / "views.py.bak"
        assert not backup.exists()
