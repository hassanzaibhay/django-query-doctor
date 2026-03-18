# Custom Plugins

django-query-doctor provides a plugin API for writing your own analyzers. Custom analyzers integrate seamlessly with the pipeline -- they receive the same captured query data and produce the same `Prescription` objects as the built-in analyzers.

---

## Creating a Custom Analyzer

Every analyzer subclasses `BaseAnalyzer` and implements the `analyze` method:

```python title="myapp/analyzers.py"
from __future__ import annotations

from query_doctor.analyzers.base import BaseAnalyzer, Prescription, Severity


class SlowQueryAnalyzer(BaseAnalyzer):
    """Detect queries that exceed a configurable time threshold."""

    name = "slow_query"
    description = "Flags individual queries that take longer than the configured threshold."

    def __init__(self, threshold_ms: float = 100.0) -> None:
        super().__init__()
        self.threshold_ms = threshold_ms

    def analyze(self, queries: list, fingerprints: dict) -> list[Prescription]:
        """Analyze captured queries and return prescriptions for slow ones.

        Args:
            queries: List of CapturedQuery objects with sql, params, time_ms,
                     stack_trace, and fingerprint attributes.
            fingerprints: Dictionary mapping fingerprint hashes to lists of
                          queries sharing that fingerprint.

        Returns:
            A list of Prescription objects for each issue found.
        """
        prescriptions = []

        for query in queries:
            if query.time_ms > self.threshold_ms:
                prescriptions.append(
                    Prescription(
                        severity=Severity.WARNING,
                        analyzer=self.name,
                        issue=(
                            f"Slow query: {query.time_ms:.1f}ms "
                            f"(threshold: {self.threshold_ms}ms)"
                        ),
                        table=self._extract_table(query.sql),
                        location=query.stack_trace.user_location,
                        fix=f"Consider adding an index or optimizing: {query.sql[:80]}...",
                        query_count=1,
                        time_saved_ms=query.time_ms - self.threshold_ms,
                        fingerprint=query.fingerprint,
                    )
                )

        return prescriptions

    def _extract_table(self, sql: str) -> str:
        """Extract the primary table name from a SQL statement."""
        sql_upper = sql.upper()
        if "FROM" in sql_upper:
            parts = sql.split("FROM")
            if len(parts) > 1:
                table_part = parts[1].strip().split()[0]
                return table_part.strip('"').strip("'").strip("`")
        return "unknown"
```

### The `analyze` Method

This is the only method you must implement. It receives:

| Parameter | Type | Description |
|---|---|---|
| `queries` | `list[CapturedQuery]` | All queries captured during the request/scope |
| `fingerprints` | `dict[str, list[CapturedQuery]]` | Queries grouped by their fingerprint hash |

Each `CapturedQuery` object has:

| Attribute | Type | Description |
|---|---|---|
| `sql` | `str` | The raw SQL string |
| `params` | `tuple` | Query parameters |
| `time_ms` | `float` | Execution time in milliseconds |
| `stack_trace` | `StackTrace` | Full Python stack trace with `user_location` property |
| `fingerprint` | `str` | SHA-256 hash of the normalized SQL |

### The `Prescription` Dataclass

Your analyzer must return a list of `Prescription` objects. Each one represents a single actionable finding:

```python
@dataclass
class Prescription:
    severity: Severity        # CRITICAL, WARNING, or INFO
    analyzer: str             # Your analyzer's name
    issue: str                # Human-readable description
    table: str                # Affected database table
    location: Location        # File path and line number
    fix: str                  # Suggested code fix
    query_count: int          # Number of queries involved
    time_saved_ms: float      # Estimated savings
    fingerprint: str          # Query fingerprint
```

---

## Registering via Entry Points

To make your analyzer discoverable by django-query-doctor, register it as a Python entry point in your `pyproject.toml`:

```toml title="pyproject.toml"
[project.entry-points."query_doctor.analyzers"]
slow_query = "myapp.analyzers:SlowQueryAnalyzer"
```

If you use `setup.cfg` or `setup.py`:

```ini title="setup.cfg"
[options.entry_points]
query_doctor.analyzers =
    slow_query = myapp.analyzers:SlowQueryAnalyzer
```

After installing your package (or reinstalling in editable mode), the analyzer is automatically discovered.

---

## Enabling in Settings

Once registered, enable your analyzer in your Django settings:

```python title="settings.py"
QUERY_DOCTOR = {
    "ANALYZERS": [
        # Built-in analyzers
        "nplusone",
        "duplicate",
        "missing_index",
        "fat_select",
        "queryset_eval",
        "drf_serializer",
        "query_complexity",
        # Your custom analyzer
        "slow_query",
    ],
}
```

If you omit the `ANALYZERS` setting entirely, all registered analyzers (built-in and custom) are enabled by default.

### Passing Configuration to Your Analyzer

Custom analyzers can receive configuration via the `ANALYZER_OPTIONS` setting:

```python title="settings.py"
QUERY_DOCTOR = {
    "ANALYZER_OPTIONS": {
        "slow_query": {
            "threshold_ms": 50.0,  # Flag queries slower than 50ms
        },
    },
}
```

The keyword arguments are passed to your analyzer's `__init__` method.

---

## Full Example: Connection Count Analyzer

Here is a more complete example that detects when a request opens too many database connections:

```python title="myapp/analyzers.py"
from __future__ import annotations

from collections import Counter

from query_doctor.analyzers.base import BaseAnalyzer, Prescription, Severity


class ConnectionCountAnalyzer(BaseAnalyzer):
    """Detect requests that use an excessive number of database connections."""

    name = "connection_count"
    description = "Flags requests using more database connections than expected."

    def __init__(self, max_connections: int = 1) -> None:
        super().__init__()
        self.max_connections = max_connections

    def analyze(self, queries: list, fingerprints: dict) -> list[Prescription]:
        """Check if queries span multiple database connections.

        Args:
            queries: List of CapturedQuery objects.
            fingerprints: Queries grouped by fingerprint hash.

        Returns:
            Prescriptions if too many connections are used.
        """
        prescriptions = []

        # Count unique database aliases used
        db_aliases = Counter(q.database for q in queries if hasattr(q, "database"))

        if len(db_aliases) > self.max_connections:
            prescriptions.append(
                Prescription(
                    severity=Severity.INFO,
                    analyzer=self.name,
                    issue=(
                        f"Request used {len(db_aliases)} database connections "
                        f"(expected at most {self.max_connections})"
                    ),
                    table="*",
                    location=queries[0].stack_trace.user_location if queries else None,
                    fix="Review database routing. Consider consolidating queries to a single connection.",
                    query_count=len(queries),
                    time_saved_ms=0.0,
                    fingerprint="",
                )
            )

        return prescriptions
```

---

## Testing Your Analyzer

Test custom analyzers using the same patterns as the built-in ones:

```python title="tests/test_slow_query_analyzer.py"
import pytest
from unittest.mock import MagicMock

from myapp.analyzers import SlowQueryAnalyzer


class TestSlowQueryAnalyzer:
    """Tests for the SlowQueryAnalyzer custom plugin."""

    def test_detects_slow_query(self):
        """Positive case: a query exceeding the threshold is flagged."""
        analyzer = SlowQueryAnalyzer(threshold_ms=100.0)

        query = MagicMock()
        query.sql = 'SELECT * FROM "myapp_book" WHERE "published" = true'
        query.time_ms = 250.0
        query.fingerprint = "abc123"
        query.stack_trace.user_location = MagicMock()

        prescriptions = analyzer.analyze([query], {"abc123": [query]})

        assert len(prescriptions) == 1
        assert prescriptions[0].severity.name == "WARNING"
        assert "250.0ms" in prescriptions[0].issue

    def test_ignores_fast_query(self):
        """Negative case: a fast query is not flagged."""
        analyzer = SlowQueryAnalyzer(threshold_ms=100.0)

        query = MagicMock()
        query.time_ms = 5.0

        prescriptions = analyzer.analyze([query], {})

        assert len(prescriptions) == 0

    def test_custom_threshold(self):
        """Edge case: threshold boundary."""
        analyzer = SlowQueryAnalyzer(threshold_ms=50.0)

        query = MagicMock()
        query.sql = 'SELECT 1 FROM "myapp_book"'
        query.time_ms = 50.0  # Exactly at threshold
        query.fingerprint = "def456"

        prescriptions = analyzer.analyze([query], {"def456": [query]})

        # At threshold, not over -- should not flag
        assert len(prescriptions) == 0
```

---

## Further Reading

- [How It Works](how-it-works.md) -- The analysis pipeline your analyzer plugs into.
- [Query Ignore](query-ignore.md) -- Users can suppress specific analyzer results.
- [Configuration](../getting-started/configuration.md) -- All available settings.
