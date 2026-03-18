# Reporters Overview

django-query-doctor ships with five reporters that control how analysis results
are presented. Each reporter receives the same list of `Prescription` objects
from the analyzers and formats them for a different audience or workflow.

## Available Reporters

| Reporter | Output Type | Best For | Documentation |
|----------|------------|----------|---------------|
| [Console (Rich)](console.md) | Terminal text with color and formatting | Local development, interactive debugging | [console.md](console.md) |
| [JSON](json.md) | Structured `.json` files | CI/CD pipelines, automated tooling, scripting | [json.md](json.md) |
| [HTML Dashboard](html.md) | Standalone `.html` report | Team reviews, audits, stakeholder presentations | [html.md](html.md) |
| [Log File](log.md) | Python `logging` output | Integration with existing logging infrastructure | [log.md](log.md) |
| [OpenTelemetry](opentelemetry.md) | OTel span attributes and events | Observability platforms (Jaeger, Datadog, New Relic) | [opentelemetry.md](opentelemetry.md) |

## Configuring Reporters

### Single Reporter

By default, only the Console reporter is active:

```python title="settings.py"
QUERY_DOCTOR = {
    "REPORTERS": [
        "query_doctor.reporters.ConsoleReporter",
    ],
}
```

### Multiple Reporters

You can activate several reporters simultaneously. Each one receives the same
prescriptions independently:

```python title="settings.py"
QUERY_DOCTOR = {
    "REPORTERS": [
        "query_doctor.reporters.ConsoleReporter",
        "query_doctor.reporters.JSONReporter",
        "query_doctor.reporters.HTMLReporter",
        "query_doctor.reporters.LogReporter",
        "query_doctor.reporters.OpenTelemetryReporter",
    ],

    # Reporter-specific settings
    "JSON_OUTPUT_DIR": "reports/json/",
    "HTML_OUTPUT_DIR": "reports/html/",
    "LOG_LOGGER_NAME": "query_doctor",
    "OTEL_SERVICE_NAME": "my-django-app",
}
```

!!! tip "Development vs CI"
    Use `ConsoleReporter` during local development for immediate feedback, and
    add `JSONReporter` in CI to produce machine-readable artifacts that can fail
    builds or be archived.

### Environment-Based Reporter Selection

```python title="settings.py"
import os

_reporters = ["query_doctor.reporters.ConsoleReporter"]

if os.getenv("CI"):
    _reporters = [
        "query_doctor.reporters.JSONReporter",
        "query_doctor.reporters.HTMLReporter",
    ]

QUERY_DOCTOR = {
    "REPORTERS": _reporters,
}
```

## Reporter Interface

All reporters implement the same interface:

```python
class BaseReporter(ABC):
    @abstractmethod
    def report(self, prescriptions: list[Prescription], metadata: RequestMetadata) -> None:
        """Format and output the prescriptions from a single request."""
        ...
```

This makes it straightforward to write custom reporters. See the
[Contributing Guide](../contributing.md) for details on adding new reporters.

## Filtering Output

All reporters respect the global `MIN_SEVERITY` setting:

```python title="settings.py"
QUERY_DOCTOR = {
    "MIN_SEVERITY": "WARNING",  # Only report WARNING and CRITICAL
}
```

Severity levels from lowest to highest: `DEBUG`, `INFO`, `WARNING`, `CRITICAL`.
