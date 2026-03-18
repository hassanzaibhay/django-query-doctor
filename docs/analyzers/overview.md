# Analyzers Overview

django-query-doctor ships with seven built-in analyzers. Each one targets a
specific category of ORM performance issue, receives fingerprinted query data
captured during a request, and returns **Prescription** objects that describe
the problem, its severity, and the exact code change needed to fix it.

## How Analyzers Work

The analysis pipeline follows four stages:

1. **INTERCEPT** -- the middleware installs an `execute_wrapper` that records
   every SQL query together with its Python stack trace.
2. **FINGERPRINT** -- each captured query is normalized (literal values replaced
   with placeholders) and hashed so that structurally identical queries share a
   single fingerprint.
3. **ANALYZE** -- every enabled analyzer receives the full list of fingerprinted
   queries and inspects them for a specific issue pattern.
4. **REPORT** -- the collected `Prescription` objects are handed to a reporter
   (console, JSON, or HTML) for output.

Each analyzer subclasses `BaseAnalyzer` and implements a single method:

```python
class BaseAnalyzer(ABC):
    @abstractmethod
    def analyze(self, queries: list[CapturedQuery]) -> list[Prescription]:
        """Examine captured queries and return prescriptions for any issues found."""
        ...
```

A `Prescription` contains:

| Field          | Type   | Description                                         |
|----------------|--------|-----------------------------------------------------|
| `severity`     | `str`  | `"high"`, `"medium"`, or `"low"`                    |
| `issue`        | `str`  | Human-readable description of the problem            |
| `location`     | `str`  | `file:line` reference in user code                   |
| `suggestion`   | `str`  | The exact code fix as a string                       |
| `analyzer`     | `str`  | Name of the analyzer that produced the prescription  |

## Built-in Analyzers

| Analyzer | Detects | Default Severity | Documentation |
|----------|---------|-------------------|---------------|
| [N+1 Query](nplusone.md) | Repeated queries caused by accessing related objects inside loops | high | [nplusone.md](nplusone.md) |
| [Duplicate Query](duplicate.md) | Identical SQL executed multiple times within the same request | medium | [duplicate.md](duplicate.md) |
| [Missing Index](missing-index.md) | Filters, ordering, or grouping on columns that lack a database index | medium | [missing-index.md](missing-index.md) |
| [Fat SELECT](fat-select.md) | Selecting all columns when only a subset is used | low | [fat-select.md](fat-select.md) |
| [QuerySet Evaluation](queryset-eval.md) | Unintended queryset evaluation patterns such as `len()` vs `.count()` | medium | [queryset-eval.md](queryset-eval.md) |
| [DRF Serializer](drf-serializer.md) | N+1 queries originating from Django REST Framework serializer nesting | high | [drf-serializer.md](drf-serializer.md) |
| [Query Complexity](query-complexity.md) | Overly complex SQL with excessive JOINs, subqueries, or aggregations | low | [query-complexity.md](query-complexity.md) |

## Disabling Specific Analyzers

By default all analyzers are enabled. To disable one or more, set
`QUERY_DOCTOR_DISABLED_ANALYZERS` in your Django settings:

```python
# settings.py

QUERY_DOCTOR = {
    "DISABLED_ANALYZERS": [
        "query_doctor.analyzers.fat_select.FatSelectAnalyzer",
        "query_doctor.analyzers.query_complexity.QueryComplexityAnalyzer",
    ],
}
```

You can also disable analyzers on a per-request basis using the
`@diagnose` decorator or the `diagnose_queries()` context manager:

```python
from query_doctor.decorators import diagnose

@diagnose(disabled_analyzers=["FatSelectAnalyzer"])
def my_view(request):
    ...
```

## Custom Analyzer Plugins

You can write your own analyzer by subclassing `BaseAnalyzer` and registering it
via the `QUERY_DOCTOR["EXTRA_ANALYZERS"]` setting. See the
[Custom Plugins Guide](../guides/custom-plugins.md) for a full walkthrough.
