"""Baseline snapshot for query regression detection.

Saves a snapshot of known query issues to a JSON file. Subsequent runs
compare against the baseline and report only NEW issues (regressions).

Usage:
    # Create baseline
    python manage.py check_queries --save-baseline=.query-baseline.json

    # Check against baseline (only report new issues)
    python manage.py check_queries --baseline=.query-baseline.json

    # In CI: fail only on regressions
    python manage.py check_queries --baseline=.query-baseline.json --fail-on-regression
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from query_doctor.exceptions import QueryDoctorError


class BaselineError(QueryDoctorError):
    """Raised when baseline operations fail."""


class BaselineSnapshot:
    """A snapshot of known query issues for regression detection."""

    def __init__(self, issues: list[dict[str, Any]]) -> None:
        """Initialize with a list of issue dicts.

        Args:
            issues: List of serialized prescription dicts.
        """
        self.issues = issues
        self._issue_hashes = {self._hash_issue(i) for i in issues}

    @staticmethod
    def _hash_issue(issue: dict[str, Any]) -> str:
        """Create a stable hash for an issue (ignoring line numbers).

        Line numbers change with code edits, so we hash on the stable
        properties: analyzer type, file path, and message.

        Args:
            issue: A serialized prescription dict.

        Returns:
            A 16-char hex digest identifying this issue.
        """
        key = (
            f"{issue.get('analyzer', issue.get('issue_type', ''))}:"
            f"{issue.get('file_path', issue.get('callsite', {}).get('filepath', ''))}:"
            f"{issue.get('message', issue.get('description', ''))}"
        )
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def is_known(self, issue: dict[str, Any]) -> bool:
        """Check if an issue exists in the baseline.

        Args:
            issue: A serialized prescription dict.

        Returns:
            True if this issue was in the baseline snapshot.
        """
        return self._hash_issue(issue) in self._issue_hashes

    def find_regressions(self, current_issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return issues that are NOT in the baseline (new regressions).

        Args:
            current_issues: List of current serialized prescriptions.

        Returns:
            List of new issues not present in the baseline.
        """
        return [i for i in current_issues if not self.is_known(i)]

    def find_resolved(self, current_issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return baseline issues that are no longer present (fixed).

        Args:
            current_issues: List of current serialized prescriptions.

        Returns:
            List of baseline issues that have been resolved.
        """
        current_hashes = {self._hash_issue(i) for i in current_issues}
        return [i for i in self.issues if self._hash_issue(i) not in current_hashes]

    def save(self, path: str | Path) -> Path:
        """Save baseline to a JSON file.

        Args:
            path: File path to write the baseline.

        Returns:
            The resolved Path that was written.
        """
        resolved = Path(path)
        resolved.write_text(
            json.dumps(
                {
                    "version": "2.0.0",
                    "issue_count": len(self.issues),
                    "issues": self.issues,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return resolved

    @classmethod
    def load(cls, path: str | Path) -> BaselineSnapshot:
        """Load baseline from a JSON file.

        Args:
            path: File path to read the baseline from.

        Returns:
            A BaselineSnapshot instance.

        Raises:
            BaselineError: If the file cannot be read or parsed.
        """
        resolved = Path(path)
        try:
            data = json.loads(resolved.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise BaselineError(f"Failed to load baseline from {path}: {e}") from e
        return cls(issues=data.get("issues", []))

    def __len__(self) -> int:
        """Return the number of issues in the baseline."""
        return len(self.issues)
