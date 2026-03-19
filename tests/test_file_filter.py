"""Tests for per-file and per-module prescription filtering."""

from __future__ import annotations

from query_doctor.filters.file_filter import PrescriptionFilter
from query_doctor.types import CallSite, IssueType, Prescription, Severity


def _make_prescription(filepath: str | None = None) -> Prescription:
    """Create a test prescription with an optional callsite filepath."""
    callsite = None
    if filepath is not None:
        callsite = CallSite(
            filepath=filepath,
            line_number=10,
            function_name="test_func",
            code_context="some code",
        )
    return Prescription(
        issue_type=IssueType.N_PLUS_ONE,
        severity=Severity.WARNING,
        description="Test issue",
        fix_suggestion="Fix it",
        callsite=callsite,
    )


class TestPrescriptionFilterNoFilter:
    """When no patterns are set, all prescriptions pass through."""

    def test_no_filter_matches_all(self):
        """No file or module patterns → all prescriptions match."""
        pf = PrescriptionFilter()
        prescriptions = [
            _make_prescription("myapp/views.py"),
            _make_prescription("otherapp/models.py"),
            _make_prescription(None),
        ]

        result = pf.filter(prescriptions)
        assert len(result) == 3

    def test_is_active_false_when_no_patterns(self):
        """is_active returns False when no patterns configured."""
        pf = PrescriptionFilter()
        assert pf.is_active is False

    def test_empty_lists_match_all(self):
        """Explicitly empty lists → all prescriptions match."""
        pf = PrescriptionFilter(file_patterns=[], module_patterns=[])
        prescriptions = [_make_prescription("myapp/views.py")]

        result = pf.filter(prescriptions)
        assert len(result) == 1


class TestPrescriptionFilterByFile:
    """File pattern matching tests."""

    def test_file_exact_match(self):
        """Exact file path match."""
        pf = PrescriptionFilter(file_patterns=["myapp/views.py"])
        prescriptions = [
            _make_prescription("myapp/views.py"),
            _make_prescription("myapp/models.py"),
        ]

        result = pf.filter(prescriptions)
        assert len(result) == 1
        assert result[0].callsite.filepath == "myapp/views.py"  # type: ignore[union-attr]

    def test_file_substring_match(self):
        """Substring match: 'views' matches 'myapp/views.py'."""
        pf = PrescriptionFilter(file_patterns=["views"])
        prescriptions = [
            _make_prescription("myapp/views.py"),
            _make_prescription("otherapp/views.py"),
            _make_prescription("myapp/models.py"),
        ]

        result = pf.filter(prescriptions)
        assert len(result) == 2

    def test_file_no_matches(self):
        """No matching files → empty output (not an error)."""
        pf = PrescriptionFilter(file_patterns=["nonexistent.py"])
        prescriptions = [
            _make_prescription("myapp/views.py"),
            _make_prescription("myapp/models.py"),
        ]

        result = pf.filter(prescriptions)
        assert len(result) == 0

    def test_multiple_file_patterns_union(self):
        """Multiple --file patterns → union of matches."""
        pf = PrescriptionFilter(file_patterns=["views.py", "models.py"])
        prescriptions = [
            _make_prescription("myapp/views.py"),
            _make_prescription("myapp/models.py"),
            _make_prescription("myapp/serializers.py"),
        ]

        result = pf.filter(prescriptions)
        assert len(result) == 2

    def test_file_filter_excludes_no_callsite(self):
        """Prescriptions without callsite don't match any file filter."""
        pf = PrescriptionFilter(file_patterns=["views.py"])
        prescriptions = [_make_prescription(None)]

        result = pf.filter(prescriptions)
        assert len(result) == 0


class TestPrescriptionFilterByModule:
    """Module pattern matching tests."""

    def test_module_match(self):
        """Module pattern matches converted filepath."""
        pf = PrescriptionFilter(module_patterns=["myapp.views"])
        prescriptions = [
            _make_prescription("myapp/views.py"),
            _make_prescription("myapp/models.py"),
        ]

        result = pf.filter(prescriptions)
        assert len(result) == 1

    def test_module_substring_match(self):
        """Module substring match."""
        pf = PrescriptionFilter(module_patterns=["myapp"])
        prescriptions = [
            _make_prescription("myapp/views.py"),
            _make_prescription("myapp/models.py"),
            _make_prescription("otherapp/views.py"),
        ]

        result = pf.filter(prescriptions)
        assert len(result) == 2

    def test_module_filter_excludes_no_callsite(self):
        """Prescriptions without callsite don't match module filter."""
        pf = PrescriptionFilter(module_patterns=["myapp.views"])
        prescriptions = [_make_prescription(None)]

        result = pf.filter(prescriptions)
        assert len(result) == 0


class TestPrescriptionFilterMixed:
    """Mixed file and module patterns."""

    def test_file_and_module_patterns_union(self):
        """File and module patterns are OR'd together."""
        pf = PrescriptionFilter(
            file_patterns=["views.py"],
            module_patterns=["otherapp.models"],
        )
        prescriptions = [
            _make_prescription("myapp/views.py"),  # matches file
            _make_prescription("otherapp/models.py"),  # matches module
            _make_prescription("myapp/serializers.py"),  # no match
        ]

        result = pf.filter(prescriptions)
        assert len(result) == 2

    def test_is_active_with_file_patterns(self):
        """is_active is True when file patterns set."""
        pf = PrescriptionFilter(file_patterns=["views.py"])
        assert pf.is_active is True

    def test_is_active_with_module_patterns(self):
        """is_active is True when module patterns set."""
        pf = PrescriptionFilter(module_patterns=["myapp"])
        assert pf.is_active is True


class TestFilepathToModule:
    """Conversion of file paths to module notation."""

    def test_simple_path(self):
        """Simple path conversion."""
        assert PrescriptionFilter._filepath_to_module("myapp/views.py") == "myapp.views"

    def test_nested_path(self):
        """Nested path conversion."""
        result = PrescriptionFilter._filepath_to_module("myapp/api/v2/views.py")
        assert result == "myapp.api.v2.views"

    def test_windows_separators(self):
        """Windows backslash separators are handled."""
        result = PrescriptionFilter._filepath_to_module("myapp\\views.py")
        assert result == "myapp.views"

    def test_no_extension(self):
        """Path without .py extension."""
        result = PrescriptionFilter._filepath_to_module("myapp/views")
        assert result == "myapp.views"

    def test_init_file(self):
        """__init__.py path."""
        result = PrescriptionFilter._filepath_to_module("myapp/__init__.py")
        assert result == "myapp.__init__"
