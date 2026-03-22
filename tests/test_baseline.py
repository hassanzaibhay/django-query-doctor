"""Tests for baseline snapshot system."""

from __future__ import annotations

import json

import pytest

from query_doctor.baseline import BaselineError, BaselineSnapshot


@pytest.fixture()
def sample_issues():
    """Sample issue dicts for testing."""
    return [
        {
            "issue_type": "n_plus_one",
            "severity": "critical",
            "description": "N+1 detected: 47 queries for Author",
            "file_path": "myapp/views.py",
            "line": 83,
            "fix_suggestion": "Add select_related('author')",
        },
        {
            "issue_type": "duplicate_query",
            "severity": "warning",
            "description": "Duplicate query: 6 identical queries",
            "file_path": "myapp/views.py",
            "line": 91,
            "fix_suggestion": "Cache the queryset result",
        },
    ]


class TestBaselineSnapshot:
    """Core baseline snapshot operations."""

    def test_create_empty(self):
        """Empty baseline has no issues."""
        baseline = BaselineSnapshot([])
        assert len(baseline) == 0

    def test_create_with_issues(self, sample_issues):
        """Baseline stores issues."""
        baseline = BaselineSnapshot(sample_issues)
        assert len(baseline) == 2

    def test_is_known_finds_existing(self, sample_issues):
        """Known issues are correctly identified."""
        baseline = BaselineSnapshot(sample_issues)
        assert baseline.is_known(sample_issues[0]) is True
        assert baseline.is_known(sample_issues[1]) is True

    def test_is_known_rejects_unknown(self, sample_issues):
        """New issues are correctly identified as unknown."""
        baseline = BaselineSnapshot(sample_issues)
        new_issue = {
            "issue_type": "missing_index",
            "severity": "warning",
            "description": "Missing index on user_id",
            "file_path": "myapp/models.py",
            "line": 42,
        }
        assert baseline.is_known(new_issue) is False

    def test_is_known_ignores_line_changes(self, sample_issues):
        """Same issue at different line is still considered known."""
        baseline = BaselineSnapshot(sample_issues)
        moved_issue = dict(sample_issues[0])
        moved_issue["line"] = 999  # Line changed
        assert baseline.is_known(moved_issue) is True


class TestRegressionDetection:
    """Finding new issues (regressions) and resolved issues."""

    def test_find_regressions(self, sample_issues):
        """New issues not in baseline are regressions."""
        baseline = BaselineSnapshot(sample_issues[:1])
        regressions = baseline.find_regressions(sample_issues)
        assert len(regressions) == 1
        assert regressions[0] == sample_issues[1]

    def test_no_regressions(self, sample_issues):
        """No regressions when all issues are known."""
        baseline = BaselineSnapshot(sample_issues)
        regressions = baseline.find_regressions(sample_issues)
        assert len(regressions) == 0

    def test_find_resolved(self, sample_issues):
        """Baseline issues no longer present are resolved."""
        baseline = BaselineSnapshot(sample_issues)
        resolved = baseline.find_resolved(sample_issues[:1])
        assert len(resolved) == 1

    def test_no_resolved(self, sample_issues):
        """No resolved issues when all baseline issues still exist."""
        baseline = BaselineSnapshot(sample_issues)
        resolved = baseline.find_resolved(sample_issues)
        assert len(resolved) == 0


class TestBaselinePersistence:
    """Save and load baseline from JSON file."""

    def test_save_and_load(self, tmp_path, sample_issues):
        """Baseline can be saved and loaded back."""
        path = tmp_path / "baseline.json"
        baseline = BaselineSnapshot(sample_issues)
        baseline.save(path)

        loaded = BaselineSnapshot.load(path)
        assert len(loaded) == len(baseline)
        assert loaded.is_known(sample_issues[0])
        assert loaded.is_known(sample_issues[1])

    def test_save_creates_valid_json(self, tmp_path, sample_issues):
        """Saved file is valid JSON with expected structure."""
        path = tmp_path / "baseline.json"
        BaselineSnapshot(sample_issues).save(path)

        data = json.loads(path.read_text())
        assert data["version"] == "2.0.0"
        assert data["issue_count"] == 2
        assert len(data["issues"]) == 2

    def test_load_missing_file(self, tmp_path):
        """Loading from a missing file raises BaselineError."""
        with pytest.raises(BaselineError):
            BaselineSnapshot.load(tmp_path / "nonexistent.json")

    def test_load_invalid_json(self, tmp_path):
        """Loading invalid JSON raises BaselineError."""
        path = tmp_path / "bad.json"
        path.write_text("not json!")
        with pytest.raises(BaselineError):
            BaselineSnapshot.load(path)

    def test_roundtrip_regression_detection(self, tmp_path, sample_issues):
        """Regressions detected correctly after save/load cycle."""
        path = tmp_path / "baseline.json"
        BaselineSnapshot(sample_issues[:1]).save(path)

        loaded = BaselineSnapshot.load(path)
        regressions = loaded.find_regressions(sample_issues)
        assert len(regressions) == 1
