"""Tests for smart prescription grouping."""

from __future__ import annotations

from query_doctor.grouping import PrescriptionGroup, group_prescriptions
from query_doctor.types import CallSite, IssueType, Prescription, Severity


def _make_prescription(
    issue_type: IssueType = IssueType.N_PLUS_ONE,
    severity: Severity = Severity.WARNING,
    description: str = "test issue",
    file_path: str = "myapp/views.py",
    line: int = 10,
    fix: str = "fix it",
) -> Prescription:
    """Helper to create test prescriptions."""
    return Prescription(
        issue_type=issue_type,
        severity=severity,
        description=description,
        fix_suggestion=fix,
        callsite=CallSite(filepath=file_path, line_number=line, function_name="test"),
    )


class TestPrescriptionGroup:
    """PrescriptionGroup properties."""

    def test_single_item_summary(self):
        """Single-item group shows the prescription description."""
        p = _make_prescription(description="N+1 detected")
        group = PrescriptionGroup(key="test", prescriptions=[p])
        assert group.summary == "N+1 detected"
        assert group.count == 1

    def test_multi_item_summary(self):
        """Multi-item group shows count and first description."""
        prescriptions = [
            _make_prescription(description="Issue 1"),
            _make_prescription(description="Issue 2"),
            _make_prescription(description="Issue 3"),
        ]
        group = PrescriptionGroup(key="test", prescriptions=prescriptions)
        assert group.count == 3
        assert "3 related issues" in group.summary
        assert "2 more" in group.summary

    def test_severity_is_max(self):
        """Group severity is the highest among members."""
        prescriptions = [
            _make_prescription(severity=Severity.INFO),
            _make_prescription(severity=Severity.CRITICAL),
            _make_prescription(severity=Severity.WARNING),
        ]
        group = PrescriptionGroup(key="test", prescriptions=prescriptions)
        assert group.severity == Severity.CRITICAL


class TestGroupByFileAnalyzer:
    """Group by file_path + issue_type (default)."""

    def test_same_file_same_type_grouped(self):
        """Same file + same analyzer → one group."""
        prescriptions = [
            _make_prescription(file_path="views.py", issue_type=IssueType.N_PLUS_ONE),
            _make_prescription(file_path="views.py", issue_type=IssueType.N_PLUS_ONE),
        ]
        groups = group_prescriptions(prescriptions, group_by="file_analyzer")
        assert len(groups) == 1
        assert groups[0].count == 2

    def test_different_files_separate_groups(self):
        """Different files → separate groups."""
        prescriptions = [
            _make_prescription(file_path="views.py", issue_type=IssueType.N_PLUS_ONE),
            _make_prescription(file_path="serializers.py", issue_type=IssueType.N_PLUS_ONE),
        ]
        groups = group_prescriptions(prescriptions, group_by="file_analyzer")
        assert len(groups) == 2

    def test_same_file_different_types(self):
        """Same file, different issue types → separate groups."""
        prescriptions = [
            _make_prescription(file_path="views.py", issue_type=IssueType.N_PLUS_ONE),
            _make_prescription(file_path="views.py", issue_type=IssueType.DUPLICATE_QUERY),
        ]
        groups = group_prescriptions(prescriptions, group_by="file_analyzer")
        assert len(groups) == 2


class TestGroupByRootCause:
    """Group by fix suggestion."""

    def test_same_fix_grouped(self):
        """Same fix suggestion → one group."""
        prescriptions = [
            _make_prescription(fix="Add select_related('author')"),
            _make_prescription(fix="Add select_related('author')"),
        ]
        groups = group_prescriptions(prescriptions, group_by="root_cause")
        assert len(groups) == 1

    def test_different_fixes_separate(self):
        """Different fix suggestions → separate groups."""
        prescriptions = [
            _make_prescription(fix="Add select_related('author')"),
            _make_prescription(fix="Add prefetch_related('books')"),
        ]
        groups = group_prescriptions(prescriptions, group_by="root_cause")
        assert len(groups) == 2


class TestGroupSorting:
    """Groups are sorted by severity then count."""

    def test_critical_before_warning(self):
        """Critical groups come first."""
        prescriptions = [
            _make_prescription(severity=Severity.WARNING, file_path="a.py"),
            _make_prescription(severity=Severity.CRITICAL, file_path="b.py"),
        ]
        groups = group_prescriptions(prescriptions, group_by="file_analyzer")
        assert groups[0].severity == Severity.CRITICAL

    def test_larger_groups_first_at_same_severity(self):
        """At same severity, larger groups come first."""
        prescriptions = [
            _make_prescription(file_path="a.py"),
            _make_prescription(file_path="b.py"),
            _make_prescription(file_path="b.py"),
        ]
        groups = group_prescriptions(prescriptions, group_by="file_analyzer")
        assert groups[0].count == 2
        assert groups[1].count == 1


class TestEmptyInput:
    """Edge cases with empty input."""

    def test_empty_prescriptions(self):
        """No prescriptions → no groups."""
        groups = group_prescriptions([], group_by="file_analyzer")
        assert len(groups) == 0
