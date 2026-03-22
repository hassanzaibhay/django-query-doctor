"""Smart grouping of related prescriptions.

Groups prescriptions by source file + analyzer, root cause, or view
so that related issues are presented as a single actionable cluster
rather than a flat list of individual prescriptions.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from query_doctor.types import Prescription, Severity


class PrescriptionGroup:
    """A group of related prescriptions with a shared root cause.

    Attributes:
        key: The grouping key string.
        prescriptions: List of prescriptions in this group.
        count: Number of prescriptions in this group.
        severity: The highest severity in the group.
        representative: The first prescription (used for display).
    """

    def __init__(self, key: str, prescriptions: list[Prescription]) -> None:
        """Initialize a prescription group.

        Args:
            key: The grouping key string.
            prescriptions: List of prescriptions in this group.
        """
        self.key = key
        self.prescriptions = prescriptions
        self.count = len(prescriptions)
        self.severity = max(
            (p.severity for p in prescriptions),
            key=lambda s: _SEVERITY_ORDER.get(s, 0),
        )
        self.representative = prescriptions[0]

    @property
    def summary(self) -> str:
        """Generate a human-readable summary of this group.

        Returns:
            A summary string describing the group.
        """
        if self.count == 1:
            return self.representative.description
        file_path = ""
        if self.representative.callsite:
            file_path = self.representative.callsite.filepath
        return (
            f"{self.count} related issues in "
            f"{file_path}: "
            f"{self.representative.description} (and {self.count - 1} more)"
        )


_SEVERITY_ORDER: dict[Severity, int] = {
    Severity.INFO: 0,
    Severity.WARNING: 1,
    Severity.CRITICAL: 2,
}


def group_prescriptions(
    prescriptions: list[Prescription],
    group_by: str = "file_analyzer",
) -> list[PrescriptionGroup]:
    """Group prescriptions into actionable clusters.

    Args:
        prescriptions: List of Prescription objects.
        group_by: Grouping strategy:
            - "file_analyzer": Group by (file_path, analyzer_name)
            - "root_cause": Group by suggested fix action
            - "view": Group by originating view/endpoint

    Returns:
        List of PrescriptionGroup objects, sorted by severity then count.
    """
    groups: dict[str, list[Prescription]] = defaultdict(list)

    for p in prescriptions:
        key = _compute_group_key(p, group_by)
        groups[key].append(p)

    result = [PrescriptionGroup(key=k, prescriptions=v) for k, v in groups.items()]
    result.sort(
        key=lambda g: (-_SEVERITY_ORDER.get(g.severity, 0), -g.count),
    )
    return result


def _compute_group_key(p: Prescription, group_by: str) -> str:
    """Compute the grouping key for a prescription.

    Args:
        p: The prescription.
        group_by: The grouping strategy name.

    Returns:
        A string key for grouping.
    """
    file_path = p.callsite.filepath if p.callsite else "unknown"
    issue_type = p.issue_type.value if p.issue_type else "unknown"

    if group_by == "root_cause":
        return p.fix_suggestion or f"{file_path}:{issue_type}"
    if group_by == "view":
        extra: dict[str, Any] = p.extra or {}
        return str(extra.get("endpoint", file_path))
    # Default: file_analyzer
    return f"{file_path}:{issue_type}"
