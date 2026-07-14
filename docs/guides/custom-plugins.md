# Custom Plugins

django-query-doctor provides a plugin API for writing your own analyzers. Custom analyzers integrate seamlessly with the pipeline -- they receive the same captured query data and produce the same `Prescription` objects as the built-in analyzers.

---

## Creating a Custom Analyzer

Every analyzer subclasses `BaseAnalyzer`, sets a `name`, and implements the `analyze` method:

```python title="myapp/analyzers.py"
from __future__ import annotations

from typing import Any

from query_doctor.analyzers.base import BaseAnalyzer
from query_doctor.types import CapturedQuery, IssueType, Prescription, Severity


class SlowQueryAnalyzer(BaseAnalyzer):
    """Detect queries that exceed a configurable time threshold."""

    name = "slow_query"

    def __init__(self, threshold_ms: float = 100.0) -> None:
        self.threshold_ms = threshold_ms

    def analyze(
        self,
        queries: list[CapturedQuery],
        models_meta: dict[str, Any] | None = None,
    ) -> list[Prescription]:
        """Analyze captured queries and return prescriptions for slow ones."""
        prescriptions = []

        for query in queries:
            if query.duration_ms > self.threshold_ms:
                prescriptions.append(
                    Prescription(
                        issue_type=IssueType.QUERY_COMPLEXITY,
                        severity=Severity.WARNING,
                        description=(
                            f"Slow query: {query.duration_ms:.1f}ms "
                            f"(threshold: {self.threshold_ms}ms)"
                        ),
                        fix_suggestion=(
                            f"Consider adding an index or optimizing: {query.sql[:80]}..."
                        ),
                        callsite=query.callsite,
                        query_count=1,
                        time_saved_ms=query.duration_ms - self.threshold_ms,
                        fingerprint=query.fingerprint,
                    )
                )

        return prescriptions
```

### The `analyze` Method

This is the only method you must implement. It receives:

| Parameter | Type | Description |
|---|---|---|
| `queries` | `list[CapturedQuery]` | All queries captured during the request/scope |
| `models_meta` | `dict[str, Any] \| None` | Optional Django model metadata; may be `None` |

Each `CapturedQuery` object has:

| Attribute | Type | Description |
|---|---|---|
| `sql` | `str` | The raw SQL string |
| `params` | `tuple \| None` | Query parameters |
| `duration_ms` | `float` | Execution time in milliseconds |
| `fingerprint` | `str` | SHA-256 hash of the normalized SQL |
| `normalized_sql` | `str` | SQL with parameter values replaced by `?` |
| `callsite` | `CallSite \| None` | User-code file path, line number, and function name |
| `is_select` | `bool` | True for SELECT statements |
| `tables` | `list[str]` | Tables referenced by the query |

### The `Prescription` Dataclass

Your analyzer must return a list of `Prescription` objects. Each one represents a single actionable finding:

```python
@dataclass
class Prescription:
    issue_type: IssueType        # Which issue category this finding belongs to
    severity: Severity           # CRITICAL, WARNING, or INFO
    description: str             # Human-readable description
    fix_suggestion: str          # Suggested code fix as a string
    callsite: CallSite | None    # File path, line number, function name
    query_count: int = 0         # Number of queries involved
    time_saved_ms: float = 0     # Estimated savings
    fingerprint: str = ""        # Query fingerprint
    extra: dict = ...            # Additional metadata
```

`IssueType`, `Severity`, `CapturedQuery`, `CallSite`, and `Prescription` are all importable from `query_doctor.types`. `IssueType` is a fixed enum; pick the closest existing member for your findings (there is no mechanism for registering new enum members).

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

After installing your package (or reinstalling in editable mode), the analyzer is automatically discovered and runs alongside the built-ins. Entry points that fail to load or are not `BaseAnalyzer` subclasses are logged and skipped -- they never crash the host app.

> **Note:** Discovery instantiates your class with **no arguments**, so every `__init__` parameter needs a default.

---

## Configuration

`ANALYZERS` in the `QUERY_DOCTOR` setting is a **dict** mapping analyzer names to option dicts (not a list of names). Your custom analyzer's name works as a key just like the built-ins, and the inherited `is_enabled()` method honors its `enabled` flag:

```python title="settings.py"
QUERY_DOCTOR = {
    "ANALYZERS": {
        "slow_query": {"enabled": True},
    },
}
```

An analyzer absent from `ANALYZERS` is enabled by default.

To make options like `threshold_ms` configurable, read them from the merged config yourself (user settings are deep-merged over the defaults, so custom keys under your analyzer's name are preserved):

```python
from query_doctor.conf import get_config


class SlowQueryAnalyzer(BaseAnalyzer):
    name = "slow_query"

    def _get_threshold(self) -> float:
        config = get_config()
        options = config.get("ANALYZERS", {}).get(self.name, {})
        return float(options.get("threshold_ms", 100.0))
```

---

## Testing Your Analyzer

Test custom analyzers using the same patterns as the built-in ones:

```python title="tests/test_slow_query_analyzer.py"
from myapp.analyzers import SlowQueryAnalyzer

from query_doctor.types import CallSite, CapturedQuery


def _make_query(duration_ms: float) -> CapturedQuery:
    return CapturedQuery(
        sql='SELECT * FROM "myapp_book" WHERE "published" = true',
        params=None,
        duration_ms=duration_ms,
        fingerprint="abc123",
        normalized_sql='select * from "myapp_book" where "published" = ?',
        callsite=CallSite(filepath="myapp/views.py", line_number=10, function_name="listing"),
        is_select=True,
        tables=["myapp_book"],
    )


class TestSlowQueryAnalyzer:
    """Tests for the SlowQueryAnalyzer custom plugin."""

    def test_detects_slow_query(self):
        """Positive case: a query exceeding the threshold is flagged."""
        analyzer = SlowQueryAnalyzer(threshold_ms=100.0)
        prescriptions = analyzer.analyze([_make_query(250.0)])
        assert len(prescriptions) == 1
        assert "250.0ms" in prescriptions[0].description

    def test_ignores_fast_query(self):
        """Negative case: a fast query is not flagged."""
        analyzer = SlowQueryAnalyzer(threshold_ms=100.0)
        assert analyzer.analyze([_make_query(5.0)]) == []

    def test_threshold_boundary(self):
        """Edge case: exactly at the threshold is not over it."""
        analyzer = SlowQueryAnalyzer(threshold_ms=50.0)
        assert analyzer.analyze([_make_query(50.0)]) == []
```

---

## Further Reading

- [How It Works](how-it-works.md) -- The analysis pipeline your analyzer plugs into.
- [Query Ignore](query-ignore.md) -- Users can suppress specific analyzer results.
- [Configuration](../getting-started/configuration.md) -- All available settings.
