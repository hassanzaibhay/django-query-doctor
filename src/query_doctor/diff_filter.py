"""Diff-aware CI mode for django-query-doctor.

Provides filtering of prescriptions to only include those whose callsite
is in a file that changed relative to a given git ref. Enables incremental
CI checks that focus on newly introduced issues.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from query_doctor.types import Prescription

logger = logging.getLogger("query_doctor")


def get_changed_files(ref: str, project_root: Path | None = None) -> set[str]:
    """Get files changed between ref and HEAD.

    Args:
        ref: Git ref to compare against (branch name, commit hash, etc.).
        project_root: Root directory of the git repository.

    Returns:
        Set of changed file paths. Empty set if git is unavailable or ref is invalid.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", ref, "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(project_root) if project_root else None,
        )
        return {line.strip() for line in result.stdout.splitlines() if line.strip()}
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        logger.warning(
            "query_doctor: failed to get changed files vs %s",
            ref,
            exc_info=True,
        )
        return set()


def filter_by_changed_files(
    prescriptions: list[Prescription],
    changed_files: set[str],
) -> list[Prescription]:
    """Keep only prescriptions whose callsite is in a changed file.

    Args:
        prescriptions: List of prescriptions to filter.
        changed_files: Set of file paths that changed.

    Returns:
        Filtered list containing only prescriptions in changed files.
    """
    if not changed_files:
        return []

    filtered: list[Prescription] = []
    for rx in prescriptions:
        if not rx.callsite:
            continue
        filepath = rx.callsite.filepath
        if any(filepath.endswith(f) or f.endswith(filepath) for f in changed_files):
            filtered.append(rx)
    return filtered
