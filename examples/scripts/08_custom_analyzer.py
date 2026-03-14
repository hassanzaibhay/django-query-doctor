#!/usr/bin/env python
"""
Example 8: Writing a Custom Analyzer Plugin
"""

print("=" * 60)
print("Example 8: Custom Analyzer Plugin")
print("=" * 60)

print("""
# Step 1: Write your analyzer

from query_doctor.analyzers.base import BaseAnalyzer
from query_doctor.types import CapturedQuery, Prescription, IssueType, Severity

class SlowQueryAnalyzer(BaseAnalyzer):
    \"\"\"Flag queries that take longer than a threshold.\"\"\"
    name = "slow_query"

    def analyze(self, queries: list[CapturedQuery], models_meta=None):
        prescriptions = []
        threshold_ms = 500  # Flag queries over 500ms

        for query in queries:
            if query.duration_ms > threshold_ms:
                prescriptions.append(Prescription(
                    issue_type=IssueType.QUERY_COMPLEXITY,
                    severity=Severity.WARNING if query.duration_ms < 1000 else Severity.CRITICAL,
                    description=f"Query took {query.duration_ms:.0f}ms (threshold: {threshold_ms}ms)",
                    fix_suggestion="Add database indexes, simplify JOINs, or cache the result",
                    callsite=query.callsite,
                ))
        return prescriptions


# Step 2: Register via entry point in your package's pyproject.toml

# [project.entry-points."query_doctor.analyzers"]
# slow_query = "my_package.analyzers:SlowQueryAnalyzer"


# Step 3: It's automatically discovered
from query_doctor.plugin_api import discover_analyzers
analyzers = discover_analyzers()
# Your SlowQueryAnalyzer is now in the list alongside built-in analyzers
""")
