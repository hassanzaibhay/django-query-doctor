"""Support for .queryignore files to suppress known false positives.

Loads ignore rules from a .queryignore file at the project root and
applies them to filter out matching queries and prescriptions from
the analysis pipeline.
"""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass
from pathlib import Path

from query_doctor.types import CapturedQuery, Prescription

logger = logging.getLogger("query_doctor")


@dataclass(frozen=True)
class IgnoreRule:
    """A single ignore rule parsed from .queryignore."""

    rule_type: str  # "sql", "file", "callsite", "ignore"
    pattern: str


def load_queryignore(project_root: Path | None = None) -> list[IgnoreRule]:
    """Load .queryignore from project root.

    Args:
        project_root: Root directory to search for .queryignore.
            Defaults to current working directory.

    Returns:
        List of parsed IgnoreRule objects. Empty list if file not found.
    """
    if project_root is None:
        project_root = _find_project_root()
    ignore_file = project_root / ".queryignore"
    if not ignore_file.exists():
        return []

    rules: list[IgnoreRule] = []
    try:
        for line in ignore_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                rule_type, _, pattern = line.partition(":")
                rules.append(IgnoreRule(rule_type=rule_type.strip(), pattern=pattern.strip()))
    except OSError:
        logger.warning(
            "query_doctor: failed to read .queryignore",
            exc_info=True,
        )

    return rules


def should_ignore_query(query: CapturedQuery, rules: list[IgnoreRule]) -> bool:
    """Check if a captured query matches any ignore rule.

    Args:
        query: The captured query to check.
        rules: List of ignore rules to match against.

    Returns:
        True if the query should be ignored.
    """
    for rule in rules:
        if rule.rule_type == "sql":
            pattern = rule.pattern.replace("%", "*")
            if fnmatch.fnmatch(query.sql, pattern):
                return True

        elif rule.rule_type == "file":
            if query.callsite and fnmatch.fnmatch(query.callsite.filepath, rule.pattern):
                return True

        elif rule.rule_type == "callsite":
            if query.callsite:
                callsite_str = f"{query.callsite.filepath}:{query.callsite.line_number}"
                if callsite_str == rule.pattern:
                    return True

    return False


def filter_prescriptions(
    prescriptions: list[Prescription],
    rules: list[IgnoreRule],
) -> list[Prescription]:
    """Remove prescriptions that match ignore rules.

    Args:
        prescriptions: List of prescriptions to filter.
        rules: List of ignore rules to apply.

    Returns:
        Filtered list with matching prescriptions removed.
    """
    if not rules:
        return list(prescriptions)

    filtered: list[Prescription] = []
    for rx in prescriptions:
        if _should_ignore_prescription(rx, rules):
            continue
        filtered.append(rx)
    return filtered


def _should_ignore_prescription(rx: Prescription, rules: list[IgnoreRule]) -> bool:
    """Check if a prescription matches any ignore rule.

    Args:
        rx: The prescription to check.
        rules: List of ignore rules.

    Returns:
        True if the prescription should be ignored.
    """
    for rule in rules:
        if rule.rule_type == "file":
            if rx.callsite and fnmatch.fnmatch(rx.callsite.filepath, rule.pattern):
                return True

        elif rule.rule_type == "callsite":
            if rx.callsite:
                callsite_str = f"{rx.callsite.filepath}:{rx.callsite.line_number}"
                if callsite_str == rule.pattern:
                    return True

        elif rule.rule_type == "ignore":
            # Format: issue_type:path:optional_name
            parts = rule.pattern.split(":", 2)
            if len(parts) >= 2:
                issue_type_str = parts[0]
                path_part = parts[1]
                if (
                    rx.callsite
                    and rx.issue_type.value == issue_type_str
                    and path_part in rx.callsite.filepath
                ):
                    return True

        elif rule.rule_type == "sql":
            # Best-effort: check if the SQL pattern appears in description
            pattern = rule.pattern.replace("%", "*")
            if fnmatch.fnmatch(rx.description, f"*{pattern}*"):
                return True

    return False


def _find_project_root() -> Path:
    """Find the project root by looking for manage.py.

    Returns:
        Path to project root, or current working directory as fallback.
    """
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / "manage.py").exists():
            return parent
    return cwd
