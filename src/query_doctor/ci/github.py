"""GitHub Actions integration for django-query-doctor.

Provides JSON output formatting and GitHub Actions annotations that show
inline in PR diff views. Also generates Markdown summaries for PR comments.
"""

from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from query_doctor.types import DiagnosisReport, Prescription, Severity


def format_github_annotations(
    prescriptions: list[Prescription],
    stream: TextIO | None = None,
) -> None:
    """Format prescriptions as GitHub Actions annotations.

    These annotations show inline in the PR diff view when used
    in a GitHub Actions workflow.

    Args:
        prescriptions: List of prescriptions to annotate.
        stream: Output stream (defaults to sys.stdout).
    """
    out = stream or sys.stdout
    for p in prescriptions:
        level = "error" if p.severity == Severity.CRITICAL else "warning"
        file_path = p.callsite.filepath if p.callsite else ""
        line = p.callsite.line_number if p.callsite else 0
        msg = p.description.replace("\n", " ")
        print(f"::{level} file={file_path},line={line}::{msg}", file=out)


def generate_pr_comment(report: DiagnosisReport) -> str:
    """Generate a Markdown PR comment body from a diagnosis report.

    Args:
        report: The diagnosis report.

    Returns:
        Markdown string suitable for a GitHub PR comment.
    """
    total = len(report.prescriptions)

    if total == 0:
        return "## Query Doctor\n\nNo query issues found. Clean bill of health!"

    lines = [
        "## Query Doctor\n",
        f"Found **{total}** query issue(s):\n",
    ]

    for p in report.prescriptions:
        severity = p.severity.value.upper()
        loc = ""
        if p.callsite:
            loc = f" ({p.callsite.filepath}:{p.callsite.line_number})"
        lines.append(f"- **{severity}**: {p.description}{loc}")

    lines.append("\n<details><summary>How to fix</summary>\n")
    for p in report.prescriptions:
        if p.fix_suggestion:
            lines.append(f"- {p.fix_suggestion}")
    lines.append("\n</details>")

    return "\n".join(lines)


def write_json_report(
    report: DiagnosisReport,
    output_path: str,
) -> None:
    """Write a diagnosis report to a JSON file.

    The JSON format is designed for consumption by CI scripts and
    the GitHub Actions workflow.

    Args:
        report: The diagnosis report.
        output_path: File path to write the JSON output.
    """
    issues: list[dict[str, Any]] = []
    for p in report.prescriptions:
        issue: dict[str, Any] = {
            "severity": p.severity.value,
            "issue_type": p.issue_type.value,
            "message": p.description,
            "suggestion": p.fix_suggestion,
            "file": p.callsite.filepath if p.callsite else "",
            "line": p.callsite.line_number if p.callsite else 0,
            "query_count": p.query_count,
        }
        issues.append(issue)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(issues, f, indent=2)
