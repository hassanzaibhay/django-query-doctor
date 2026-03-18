# OpenTelemetry Reporter

The OpenTelemetry reporter exports prescriptions as OTel span attributes and
events, integrating query health data into your existing observability stack.
Prescriptions appear alongside your application traces in platforms like Jaeger,
Datadog, New Relic, Honeycomb, and Grafana Tempo.

## Installation

The OpenTelemetry reporter requires the `otel` extras:

```bash
pip install django-query-doctor[otel]
```

This installs the required OpenTelemetry SDK packages:

- `opentelemetry-api`
- `opentelemetry-sdk`
- `opentelemetry-exporter-otlp`

!!! warning "Required dependency"
    Unlike the Console reporter, the OpenTelemetry reporter will not function
    without the OTel packages installed. If they are missing, the reporter
    logs a warning and silently skips exporting.

## Configuration

```python title="settings.py"
QUERY_DOCTOR = {
    "REPORTERS": [
        "query_doctor.reporters.OpenTelemetryReporter",
    ],

    # OpenTelemetry-specific settings
    "OTEL_SERVICE_NAME": "my-django-app",
    "OTEL_ENDPOINT": "http://localhost:4317",
    "OTEL_EXPORT_FORMAT": "otlp",          # "otlp" or "otlp-http"
    "OTEL_INCLUDE_SQL": False,
    "OTEL_SPAN_NAME_PREFIX": "query_doctor",
}
```

### Setting Details

| Setting | Default | Description |
|---------|---------|-------------|
| `OTEL_SERVICE_NAME` | `"django-app"` | Service name attached to all exported spans. Should match your application's OTel service name. |
| `OTEL_ENDPOINT` | `"http://localhost:4317"` | OTLP collector endpoint. Use port 4317 for gRPC, 4318 for HTTP. |
| `OTEL_EXPORT_FORMAT` | `"otlp"` | Export protocol. `"otlp"` uses gRPC, `"otlp-http"` uses HTTP/protobuf. |
| `OTEL_INCLUDE_SQL` | `False` | Whether to include raw SQL in span attributes. Disable in production to avoid leaking sensitive data. |
| `OTEL_SPAN_NAME_PREFIX` | `"query_doctor"` | Prefix for span names created by the reporter. |

## How It Works

The OpenTelemetry reporter operates within the context of the current request
span (created by Django's OTel instrumentation or your own setup):

1. **Span Attributes** -- summary data is added to the current request span
2. **Span Events** -- each prescription is emitted as a span event with
   structured attributes

This means prescriptions appear as part of your existing request traces rather
than as separate, disconnected spans.

## Example Span Attributes

The reporter adds these attributes to the current request span:

```
query_doctor.total_queries = 127
query_doctor.total_prescriptions = 4
query_doctor.critical_count = 1
query_doctor.warning_count = 2
query_doctor.info_count = 1
query_doctor.total_query_time_ms = 342.5
```

Each prescription is emitted as a span event:

```
Event: query_doctor.prescription
  Attributes:
    severity = "critical"
    analyzer = "NPlusOneAnalyzer"
    issue = "50 queries fetching Author for each Book"
    location.file = "myapp/views.py"
    location.line = 42
    suggestion = "Add select_related('author') to queryset"
    query_count = 50
```

## Platform Integration

### Jaeger

With Jaeger as your tracing backend, prescriptions appear in the span detail
view. Set the endpoint to your Jaeger collector:

```python title="settings.py"
QUERY_DOCTOR = {
    "OTEL_ENDPOINT": "http://jaeger-collector:4317",
    "OTEL_SERVICE_NAME": "my-django-app",
}
```

You can search for traces with query issues using Jaeger's tag search:

```
query_doctor.critical_count > 0
```

### Datadog

Datadog's OTel collector ingests OTLP data. Configure the endpoint to point
to the Datadog Agent:

```python title="settings.py"
QUERY_DOCTOR = {
    "OTEL_ENDPOINT": "http://localhost:4317",
    "OTEL_SERVICE_NAME": "my-django-app",
}
```

!!! tip "Datadog monitors"
    Create a Datadog monitor that alerts when `query_doctor.critical_count`
    exceeds 0 on production traces. This catches query regressions before
    they impact users.

### New Relic

New Relic accepts OTLP data at their cloud endpoint:

```python title="settings.py"
import os

QUERY_DOCTOR = {
    "OTEL_ENDPOINT": "https://otlp.nr-data.net:4317",
    "OTEL_SERVICE_NAME": "my-django-app",
}
```

!!! note "Authentication"
    New Relic requires an API key header for OTLP ingestion. Configure this
    through the OpenTelemetry SDK's exporter headers, not through
    django-query-doctor settings:
    ```python
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    exporter = OTLPSpanExporter(
        endpoint="https://otlp.nr-data.net:4317",
        headers={"api-key": os.getenv("NEW_RELIC_LICENSE_KEY")},
    )
    ```

### Honeycomb

```python title="settings.py"
QUERY_DOCTOR = {
    "OTEL_ENDPOINT": "https://api.honeycomb.io:443",
    "OTEL_SERVICE_NAME": "my-django-app",
}
```

## Combining with Django OTel Instrumentation

If you are already using `opentelemetry-instrumentation-django`, the
query-doctor reporter attaches to the same request spans:

```python title="settings.py"
# Standard Django OTel setup
INSTALLED_APPS = [
    ...,
    "query_doctor",
]

MIDDLEWARE = [
    "opentelemetry.instrumentation.django.middleware.OpenTelemetryMiddleware",
    ...,
    "query_doctor.middleware.QueryDoctorMiddleware",
]

QUERY_DOCTOR = {
    "REPORTERS": [
        "query_doctor.reporters.OpenTelemetryReporter",
    ],
    "OTEL_SERVICE_NAME": "my-django-app",
}
```

!!! warning "Middleware ordering"
    Place the `QueryDoctorMiddleware` **after** the OTel middleware so that
    query-doctor can attach events to the span created by the OTel middleware.

## Security Considerations

Be cautious with `OTEL_INCLUDE_SQL` in production:

- SQL statements may contain sensitive data (user IDs, emails, etc.)
- Span attributes are often stored in plain text in tracing backends
- Set `OTEL_INCLUDE_SQL: False` (the default) in production environments

```python title="settings.py"
import os

QUERY_DOCTOR = {
    "OTEL_INCLUDE_SQL": os.getenv("DJANGO_DEBUG", "false").lower() == "true",
}
```

See also: [Reporters Overview](overview.md) | [JSON Reporter](json.md) | [Log Reporter](log.md)
