"""Tests for diff-aware CI mode filtering."""

from __future__ import annotations

from unittest.mock import patch

from query_doctor.diff_filter import filter_by_changed_files, get_changed_files
from query_doctor.types import CallSite, IssueType, Prescription, Severity


def _make_prescription(filepath: str = "myapp/views.py") -> Prescription:
    """Create a Prescription with given callsite filepath."""
    return Prescription(
        issue_type=IssueType.N_PLUS_ONE,
        severity=Severity.WARNING,
        description="Test issue",
        fix_suggestion="Fix it",
        callsite=CallSite(
            filepath=filepath,
            line_number=10,
            function_name="get_queryset",
        ),
    )


class TestGetChangedFiles:
    """Tests for git diff file retrieval."""

    def test_returns_set_of_paths(self) -> None:
        """Mocked git diff should return set of file paths."""
        with patch("query_doctor.diff_filter.subprocess.run") as mock_run:
            mock_run.return_value.stdout = "myapp/views.py\nmyapp/models.py\n"
            mock_run.return_value.returncode = 0
            result = get_changed_files("main")
        assert result == {"myapp/views.py", "myapp/models.py"}

    def test_git_not_available_returns_empty(self) -> None:
        """FileNotFoundError (git not installed) should return empty set."""
        with patch("query_doctor.diff_filter.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("git not found")
            result = get_changed_files("main")
        assert result == set()

    def test_invalid_ref_returns_empty(self) -> None:
        """CalledProcessError (invalid ref) should return empty set."""
        import subprocess

        with patch("query_doctor.diff_filter.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(128, "git")
            result = get_changed_files("nonexistent-ref")
        assert result == set()

    def test_empty_output_returns_empty_set(self) -> None:
        """Empty git diff output should return empty set."""
        with patch("query_doctor.diff_filter.subprocess.run") as mock_run:
            mock_run.return_value.stdout = ""
            mock_run.return_value.returncode = 0
            result = get_changed_files("main")
        assert result == set()

    def test_blank_lines_filtered(self) -> None:
        """Blank lines in output should be filtered."""
        with patch("query_doctor.diff_filter.subprocess.run") as mock_run:
            mock_run.return_value.stdout = "file.py\n\n\nother.py\n"
            mock_run.return_value.returncode = 0
            result = get_changed_files("main")
        assert result == {"file.py", "other.py"}


class TestFilterByChangedFiles:
    """Tests for prescription filtering by changed files."""

    def test_keeps_matching_prescriptions(self) -> None:
        """Prescriptions in changed files should be kept."""
        changed = {"myapp/views.py", "myapp/models.py"}
        prescriptions = [
            _make_prescription("myapp/views.py"),
            _make_prescription("myapp/serializers.py"),
        ]
        result = filter_by_changed_files(prescriptions, changed)
        assert len(result) == 1
        assert result[0].callsite.filepath == "myapp/views.py"

    def test_removes_non_matching_prescriptions(self) -> None:
        """Prescriptions not in changed files should be removed."""
        changed = {"myapp/views.py"}
        prescriptions = [_make_prescription("other/file.py")]
        result = filter_by_changed_files(prescriptions, changed)
        assert len(result) == 0

    def test_path_matching_with_relative_and_absolute(self) -> None:
        """Path matching should work with partial/endswith matching."""
        changed = {"myapp/views.py"}
        prescriptions = [
            _make_prescription("/home/user/project/myapp/views.py"),
        ]
        result = filter_by_changed_files(prescriptions, changed)
        assert len(result) == 1

    def test_prescription_without_callsite_excluded(self) -> None:
        """Prescriptions without callsite should be excluded."""
        changed = {"myapp/views.py"}
        prescription = Prescription(
            issue_type=IssueType.N_PLUS_ONE,
            severity=Severity.WARNING,
            description="Test",
            fix_suggestion="Fix",
            callsite=None,
        )
        result = filter_by_changed_files([prescription], changed)
        assert len(result) == 0

    def test_empty_changed_files_returns_empty(self) -> None:
        """Empty changed files set should return empty list."""
        prescriptions = [_make_prescription()]
        result = filter_by_changed_files(prescriptions, set())
        assert len(result) == 0
