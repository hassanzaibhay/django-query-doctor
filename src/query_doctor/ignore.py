"""Support for .queryignore files to suppress known false positives.

Loads ignore rules from a .queryignore file at the project root and
applies them to filter out matching queries and prescriptions from
the analysis pipeline.
"""

from __future__ import annotations

import fnmatch
import logging
import warnings
from dataclasses import dataclass
from pathlib import Path

from query_doctor.exceptions import QueryDoctorWarning
from query_doctor.types import CapturedQuery, Prescription

logger = logging.getLogger("query_doctor")


@dataclass(frozen=True)
class IgnoreRule:
    """A single ignore rule parsed from .queryignore."""

    rule_type: str  # "sql", "file", "callsite", "ignore"
    pattern: str


def load_queryignore(project_root: Path | None = None) -> list[IgnoreRule]:
    """Load .queryignore rules.

    Resolution order:

    1. ``project_root`` when given -- an explicit argument always wins, so
       callers that already know the directory are unaffected by settings.
    2. The ``QUERYIGNORE_PATH`` setting, which names the ignore file itself.
    3. ``.queryignore`` beside the project root located by
       :func:`_find_project_root`.

    A configured ``QUERYIGNORE_PATH`` that does not resolve degrades to (3)
    rather than raising -- analysis must never break the host -- but it warns
    on the way. Degrading silently would make a configured path observably
    identical to never setting one, which is the failure mode
    :class:`~query_doctor.exceptions.QueryDoctorWarning` exists to report.

    Args:
        project_root: Root directory to search for .queryignore. Overrides
            the ``QUERYIGNORE_PATH`` setting when given.

    Returns:
        List of parsed IgnoreRule objects. Empty list if no file is found.
    """
    if project_root is not None:
        ignore_file = project_root / ".queryignore"
    else:
        ignore_file = _configured_ignore_file() or (_find_project_root() / ".queryignore")

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


def _configured_ignore_file() -> Path | None:
    """Return the ignore file named by QUERYIGNORE_PATH, or None.

    Returns None both when the setting is unset and when it names something
    unusable; the unusable case warns first, so the caller's fallback is
    reported rather than silent.
    """
    from query_doctor.conf import get_config

    try:
        configured = get_config().get("QUERYIGNORE_PATH")
    except Exception:
        # Settings unavailable (no Django configured); fall back quietly --
        # the user set nothing here, so there is nothing to report.
        return None

    if not configured:
        return None

    path = Path(configured)
    if path.is_file():
        return path

    reason = "it is a directory" if path.is_dir() else "no such file"
    warnings.warn(
        # Plain str, not repr: on Windows a repr doubles every backslash, so the
        # path in the warning stops matching the path the user configured.
        f"query_doctor: QUERYIGNORE_PATH is set to '{configured}' but {reason}; "
        f"the setting was ignored. Falling back to '.queryignore' beside the project "
        f"root. QUERYIGNORE_PATH must name the ignore file itself, not its directory.",
        QueryDoctorWarning,
        stacklevel=3,
    )
    return None


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
